import json

with open("data/cases/SUITE-KAN-25.json", "r", encoding="utf-8") as f:
    d = json.load(f)

tc = d["suite_data"]["test_cases"][0]
for s in tc["steps"][:31]:
    print(f"Step {s['step_number']}: action={s['action']} | strategy={s['locator_strategy']} | selector={s['selector_value']} | role={s['role_name']} | desc={s['description']}")

