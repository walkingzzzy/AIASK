from strategy_factory.application._autonomy_stage_artifacts import attach_autonomy_stage_artifacts


def test_attach_autonomy_stage_artifacts_populates_contract_fields():
    stage = attach_autonomy_stage_artifacts(
        stage={"task_count": 2},
        scan_task_artifact={"contract_version": "scan.v1", "available": True},
        bulk_task_artifact={"contract_version": "bulk.v1", "available": False},
        generated_candidates=[{"name": "candidate_a"}],
        all_experiments=[{"id": "exp_1"}],
        build_task_artifact=lambda payload: {"contract_version": "task.v1", "available": True, "task_count": payload["task_count"]},
        build_candidate_artifact=lambda items: {"contract_version": "candidate.v1", "available": True, "candidate_count": len(items)},
        build_research_evidence_artifact=lambda payload, experiments=None: {
            "contract_version": "evidence.v1",
            "available": True,
            "experiment_count": len(experiments or []),
        },
    )

    assert stage["scan_task_artifact_contract_version"] == "scan.v1"
    assert stage["scan_task_artifact_available"] is True
    assert stage["bulk_task_artifact_contract_version"] == "bulk.v1"
    assert stage["bulk_task_artifact_available"] is False
    assert stage["task_artifact_contract_version"] == "task.v1"
    assert stage["task_artifact"]["task_count"] == 2
    assert stage["candidate_artifact_contract_version"] == "candidate.v1"
    assert stage["candidate_artifact"]["candidate_count"] == 1
    assert stage["evidence_artifact_contract_version"] == "evidence.v1"
    assert stage["evidence_artifact"]["experiment_count"] == 1
