"""Server task-container capabilities exposed to the agent."""

SCRIPT_ENVIRONMENT_HELP = (
    "The server task sandbox includes curl, wget, ssh, git, jq, and Python/Node runtimes. "
    "A selected Skill is optional. Use Python subprocess to run these commands when needed. "
    "HTTP(S) requests use the configured proxy; SSH uses the sandbox SSH proxy configuration. "
    "The container root is read-only. The task work_dir is writable and shared across run_script "
    "calls in the current turn. For a missing Python package, run "
    "python -m pip install --target <work_dir>/.dependencies/python <package>; the runner adds "
    "that directory to sys.path on subsequent calls. Import it after installation by adding "
    "the directory to sys.path in the current call. For a missing Node package, run "
    "npm install --prefix <work_dir>/.dependencies/node <package>; Node resolves its modules "
    "from that directory on subsequent calls. A standalone executable may be downloaded with "
    "curl into <work_dir>/.dependencies/bin and made executable; use an absolute path or the "
    "task PATH. Do not run apt install in the read-only task container. Report installation "
    "and connectivity failures with their actual command output. Dependencies installed this "
    "way last only for the current turn; recurring Skill dependencies belong in its package."
)
