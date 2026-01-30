from setuptools import setup, find_packages

setup(
    name="akshare-mcp",
    version="2.0.0",
    packages=find_packages(where="src"),
    package_dir={"": "src"},
    install_requires=[
        "mcp>=1.0.0",
        "akshare>=1.10.0",
        "pandas>=2.0.0",
        "numpy>=1.26.0",
        "scipy>=1.11.0",
        "numba>=0.59.0",
        "asyncpg>=0.29.0",
        "pandas-ta>=0.3.14",
        "tushare>=1.4.0",
        "baostock>=0.8.8",
        "efinance>=0.5.5",
        "pydantic>=2.0.0",
    ],
    extras_require={
        "parallel": ["ray[default]>=2.9.0"],
        "dev": ["pytest>=7.0.0", "pytest-asyncio>=0.21.0", "pytest-benchmark>=4.0.0"],
    },
    entry_points={
        "console_scripts": [
            "akshare-mcp=akshare_mcp.server:main",
        ],
    },
)
