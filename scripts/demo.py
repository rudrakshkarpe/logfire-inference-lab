"""Exercise five scenarios, then print trace links without embedding credentials."""
import json
import subprocess
import sys
from pathlib import Path
from urllib.parse import urlencode

from observatory.settings import Settings

settings = Settings()
output = Path("artifacts")
output.mkdir(exist_ok=True)
results = []
for scenario in ["baseline", "queue-pressure", "slow-prefill", "interrupted-stream", "recovery"]:
    result = subprocess.run([sys.executable, "-m", "observatory.cli", "run", "--scenario", scenario,
                             "--requests", "24"], capture_output=True, text=True, check=True)
    data = json.loads(result.stdout)
    run = data["run"]
    (output / f"{scenario}.json").write_text(json.dumps(data, indent=2) + "\n")
    results.append(data)
    print(scenario, json.dumps(run["summary"]))
    if settings.observatory_project_url:
        print(settings.observatory_project_url + "?" + urlencode({"q": f"trace_id = '{run['trace_id']}'"}))
(output / "walkthrough.json").write_text(json.dumps(results, indent=2) + "\n")
