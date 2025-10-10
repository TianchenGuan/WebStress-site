import argparse
import json
import os
import re
from typing import Any, Dict, List

# Reuse validator from this repo
try:
    from validation import validate_instruction
except Exception:
    def validate_instruction(_: Dict[str, Any]) -> None:  # fallback no-op if import fails
        return


#  - Reads each tasks/raw_os/*.json.
#       - Keeps id and instruction → description.
#       - Sets template: "desktop", difficulty: "medium", time_limit: 90.
#       - Creates schema-compliant success_criteria:
#           - Always element_text_contains:Settings (weight 0.5).
#           - Adds a second criterion based on keywords in the description:
#               - volume/sound → element_text_contains:Sound|Volume
#               - wifi/network → element_text_contains:Network|Wi-Fi|Wi‑Fi
#               - bluetooth → element_text_contains:Bluetooth
#               - brightness/display → element_text_contains:Display|Brightness
#               - font/text/zoom → element_text_contains:Accessibility|Text|Zoom
#               - otherwise → element_text_contains:Done|Success|Applied
#       - Validates each output with the repo’s validate_instruction.
#       - Writes per-file JSONs into instructions/raw_os/ and an aggregate JSONL to instructions/raw_os_converted.jsonl:1.

def _slugify(text: str, max_len: int = 40) -> str:
    t = text.lower()
    t = re.sub(r"[^a-z0-9]+", "-", t).strip("-")
    if len(t) > max_len:
        t = t[:max_len].rstrip("-")
    return t or "task"


def _criteria_from_text(desc: str) -> List[Dict[str, Any]]:
    d = desc.lower()
    crit: List[Dict[str, Any]] = []
    crit.append({"predicate": "element_text_contains:Settings", "weight": 0.5})
    if any(k in d for k in ["volume", "sound", "speaker", "audio"]):
        crit.append({"predicate": "element_text_contains:Sound|Volume", "weight": 0.5})
    elif any(k in d for k in ["wifi", "wi-fi", "network", "internet"]):
        crit.append({"predicate": "element_text_contains:Network|Wi-Fi|Wi‑Fi", "weight": 0.5})
    elif any(k in d for k in ["bluetooth"]):
        crit.append({"predicate": "element_text_contains:Bluetooth", "weight": 0.5})
    elif any(k in d for k in ["brightness", "dim", "dark"]):
        crit.append({"predicate": "element_text_contains:Display|Brightness", "weight": 0.5})
    elif any(k in d for k in ["font", "text size", "enlarge", "magnify", "zoom"]):
        crit.append({"predicate": "element_text_contains:Accessibility|Text|Zoom", "weight": 0.5})
    else:
        crit.append({"predicate": "element_text_contains:Done|Success|Applied", "weight": 0.5})
    return crit


def convert_one(raw: Dict[str, Any]) -> Dict[str, Any]:
    desc = str(raw.get("instruction") or raw.get("description") or "Desktop task")
    rid = str(raw.get("id") or _slugify(desc))
    out: Dict[str, Any] = {
        "id": rid,
        "description": desc,
        "template": "desktop",
        "difficulty": "medium",
        "time_limit": 90,
        "success_criteria": _criteria_from_text(desc),
    }
    validate_instruction(out)
    return out


def main() -> None:
    p = argparse.ArgumentParser(description="Convert tasks/raw_os/*.json to Instruction JSONs usable by orchestrator.")
    p.add_argument("--input", default="tasks/raw_os", help="Input directory containing raw OS task JSON files")
    p.add_argument("--out-jsonl", default="instructions/raw_os_converted.jsonl", help="Output JSONL path with one instruction per line")
    p.add_argument("--out-dir", default="instructions/raw_os", help="Directory to write individual instruction JSON files")
    args = p.parse_args()

    in_dir = args.input
    os.makedirs(os.path.dirname(args.out_jsonl), exist_ok=True)
    os.makedirs(args.out_dir, exist_ok=True)

    files = [
        os.path.join(in_dir, f)
        for f in os.listdir(in_dir)
        if f.endswith(".json") and os.path.isfile(os.path.join(in_dir, f))
    ]
    files.sort()
    count = 0
    with open(args.out_jsonl, "w", encoding="utf-8") as outjl:
        for path in files:
            try:
                with open(path, "r", encoding="utf-8") as f:
                    raw = json.load(f)
                instr = convert_one(raw)
                outjl.write(json.dumps(instr, ensure_ascii=False, sort_keys=True) + "\n")
                out_path = os.path.join(args.out_dir, f"{instr['id']}.json")
                with open(out_path, "w", encoding="utf-8") as outf:
                    json.dump(instr, outf, indent=2, ensure_ascii=False, sort_keys=True)
                count += 1
            except Exception as e:
                # Skip malformed entries but continue
                print(f"Skipping {path}: {e}")
                continue
    print(f"Converted {count} tasks to {args.out_jsonl} and {args.out_dir}/")


if __name__ == "__main__":
    main()

