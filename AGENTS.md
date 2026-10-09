You are building Sunny V2. Read docs/spec/LAB_RUN.md first; this file overrides it where they conflict.
You are running INSIDE the sunny-sandbox container. Run python, pytest, npm and other commands directly. Do not use docker exec. Docker is not available here.
Do not run git or push_checkpoint.sh. The human checkpoints from the host.
If an acceptance check needs docker compose (e.g. P0), write the exact command in BLOCKERS.md for the human to run, then continue.
Never edit lab/. Update PROGRESS.md before ending every task.
