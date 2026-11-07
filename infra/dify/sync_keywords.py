"""Copies moderation-keywords.txt and preset-responses.json into the runner DSL's content moderation.

    uv run --project backend python infra/dify/sync_keywords.py          # update eduagent-runner.yml
    uv run --project backend python infra/dify/sync_keywords.py --check  # exit 1 if the DSL is out of date

After updating, import eduagent-runner.yml again in Dify Studio (or paste the keywords into its moderation settings).
eduagent-runner-raw.yml keeps moderation off and is only checked for that.
"""

import json
import sys
from pathlib import Path

import yaml

HERE = Path(__file__).resolve().parent
RUNNER = HERE / "eduagent-runner.yml"
RAW = HERE / "eduagent-runner-raw.yml"


def keywords_text() -> str:
    lines = (HERE / "moderation-keywords.txt").read_text(encoding="utf-8").splitlines()
    return "\n".join(line.strip() for line in lines if line.strip() and not line.lstrip().startswith("#"))


def expected_moderation() -> dict:
    presets = json.loads((HERE / "preset-responses.json").read_text(encoding="utf-8"))
    return {
        "enabled": True,
        "type": "keywords",
        "config": {
            "keywords": keywords_text(),
            "inputs_config": {"enabled": True, "preset_response": presets["input_blocked"]},
            "outputs_config": {"enabled": True, "preset_response": presets["output_blocked"]},
        },
    }


def moderation_of(dsl: dict) -> dict:
    return dsl["workflow"]["features"]["sensitive_word_avoidance"]


def problems() -> list[str]:
    found = []
    runner = yaml.safe_load(RUNNER.read_text(encoding="utf-8"))
    if moderation_of(runner) != expected_moderation():
        found.append(f"{RUNNER.name}: content moderation differs from moderation-keywords.txt / preset-responses.json")
    raw = yaml.safe_load(RAW.read_text(encoding="utf-8"))
    if moderation_of(raw).get("enabled"):
        found.append(f"{RAW.name}: content moderation must stay off")
    without = [{**dsl, "app": None, "workflow": {**dsl["workflow"], "features": None}} for dsl in (runner, raw)]
    if without[0] != without[1]:
        found.append(f"{RAW.name}: must match {RUNNER.name} except app info and content moderation")
    return found


def sync() -> None:
    text = RUNNER.read_text(encoding="utf-8")
    header = "".join(line + "\n" for line in text.splitlines() if line.startswith("#"))
    dsl = yaml.safe_load(text)
    dsl["workflow"]["features"]["sensitive_word_avoidance"] = expected_moderation()
    with RUNNER.open("w", encoding="utf-8", newline="\n") as out:
        out.write(header)
        yaml.dump(dsl, out, allow_unicode=True, sort_keys=False, width=120)


if __name__ == "__main__":
    if "--check" in sys.argv:
        issues = problems()
        for issue in issues:
            print(issue)
        sys.exit(1 if issues else 0)
    sync()
    print(f"updated {RUNNER.name}")
