import re

def test_frontend():
    with open("frontend/templates/index.html", "r", encoding="utf-8") as f:
        content = f.read()

    # Find all document.getElementById calls
    js_ids = re.findall(r'document\.getElementById\([\'"]([^\'"]+)[\'"]\)', content)

    # Exclude any dynamically created or handled IDs
    js_ids = set(js_ids)

    missing = []
    for elem_id in js_ids:
        # Check if id="elem_id" exists in the HTML part
        if f'id="{elem_id}"' not in content and f"id='{elem_id}'" not in content:
            # Maybe it's a dynamic prefix like "page-" + page
            if "page-" not in elem_id:
                missing.append(elem_id)

    if missing:
        print("Frontend Verification Failed!")
        print("The following IDs are referenced in JS but not found in HTML:")
        for m in missing:
            print(f" - {m}")
        exit(1)
    else:
        print("Frontend Verification Passed: All referenced IDs exist in HTML.")

if __name__ == "__main__":
    test_frontend()
