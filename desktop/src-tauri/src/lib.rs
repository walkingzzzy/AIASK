use std::env;
use std::io;
use std::path::PathBuf;
use std::process::{Child, Command, Stdio};
use std::sync::Mutex;
use tauri::{Manager, RunEvent};

fn exe_name(base: &str) -> String {
    if cfg!(windows) {
        format!("{base}.exe")
    } else {
        base.to_string()
    }
}

fn command_available(command: &str) -> bool {
    Command::new(command)
        .arg("--version")
        .stdout(Stdio::null())
        .stderr(Stdio::null())
        .status()
        .is_ok()
}

fn agent_workdir() -> Option<PathBuf> {
    if let Ok(value) = env::var("AIASK_AGENT_WORKDIR") {
        let path = PathBuf::from(value);
        if path.exists() {
            return Some(path);
        }
    }
    let manifest_dir = PathBuf::from(env!("CARGO_MANIFEST_DIR"));
    let candidate = manifest_dir.join("../../packages/agent");
    if candidate.exists() {
        return candidate.canonicalize().ok().or(Some(candidate));
    }
    None
}

fn command_from_shell(script: &str) -> Command {
    if cfg!(windows) {
        let mut command = Command::new("cmd");
        command.arg("/C").arg(script);
        command
    } else {
        let mut command = Command::new("sh");
        command.arg("-c").arg(script);
        command
    }
}

fn spawn_direct_agent(binary: PathBuf, port: &str) -> Command {
    let mut command = Command::new(binary);
    command.arg("--port").arg(port);
    command
}

fn spawn_agent(app: &tauri::App) -> io::Result<Child> {
    let port = env::var("AIASK_AGENT_PORT").unwrap_or_else(|_| "8767".to_string());
    let mut command = if let Ok(script) = env::var("AIASK_AGENT_CMD") {
        command_from_shell(&script)
    } else if let Ok(binary) = env::var("AIASK_AGENT_BIN") {
        spawn_direct_agent(PathBuf::from(binary), &port)
    } else if let Ok(resource_dir) = app.path().resource_dir() {
        let sidecar = resource_dir.join("sidecars").join(exe_name("aiask-agent"));
        let flat = resource_dir.join(exe_name("aiask-agent"));
        if sidecar.exists() {
            spawn_direct_agent(sidecar, &port)
        } else if flat.exists() {
            spawn_direct_agent(flat, &port)
        } else if command_available("aiask-agent") {
            spawn_direct_agent(PathBuf::from("aiask-agent"), &port)
        } else {
            let mut command = Command::new("uv");
            command.arg("run").arg("aiask-agent").arg("--port").arg(&port);
            command
        }
    } else if command_available("aiask-agent") {
        spawn_direct_agent(PathBuf::from("aiask-agent"), &port)
    } else {
        let mut command = Command::new("uv");
        command.arg("run").arg("aiask-agent").arg("--port").arg(&port);
        command
    };

    if env::var("AIASK_AGENT_CMD").is_err() {
        if let Some(workdir) = agent_workdir() {
            command.current_dir(workdir);
        }
    }
    command.env("AIASK_AGENT_PORT", &port);
    command.stdout(Stdio::inherit()).stderr(Stdio::inherit()).spawn()
}

pub fn run() {
    let agent_child = std::sync::Arc::new(Mutex::new(None));
    let agent_child_clone = agent_child.clone();

    let app = tauri::Builder::default()
        .setup(move |app| {
            println!("Starting aiask-agent...");
            match spawn_agent(app) {
                Ok(child) => {
                    *agent_child.lock().unwrap() = Some(child);
                }
                Err(error) => {
                    eprintln!(
                        "AIASK agent was not started: {error}. Desktop will open and can connect to a running Agent endpoint."
                    );
                }
            }
            Ok(())
        })
        .build(tauri::generate_context!())
        .expect("error while building AIASK desktop");

    app.run(move |_app_handle, event| {
        if let RunEvent::ExitRequested { .. } = event {
            println!("Closing aiask-agent...");
            if let Some(mut child) = agent_child_clone.lock().unwrap().take() {
                let _ = child.kill();
                let _ = child.wait();
            }
        }
    });
}
