# WebAgentBench — Sample Human Task Previews

Generated 2026-04-30 by `webagentbench/human/preview_assignment.py --launch-probe` against current HEAD.

Each sample shows what the annotator sees (section A) and what
internal metadata + trace paths exist (section B). Live instruction
rendering is enabled — actual `seed=42` API session is created and
deleted, no trace recorded.

---

# Sample: Weili (primary, index 0)

## A. Human-facing preview (what the annotator sees)

**Task title:** Add a New Shipping Address
**Website:** amazon

**Resolved instruction (rendered at seed 42):**

> Go to your account settings and add a new shipping address with name "Jordan Lee", street "742 Evergreen Terrace", city "Portland", state "OR", and ZIP code "97201".

**Recording flow:**
1. Click Start on the dashboard card.
2. Read the resolved instruction in the Control tab. A 10-s countdown auto-starts the recorder; click Start now to begin earlier.
3. Cold attempt: switch to the env tab, perform the task. Click Evaluate when done. Trace saves under .../cold/.
4. Click Start warm attempt → ; env resets at the same seed.
5. Warm attempt: redo the task using what you learned in cold. Click Evaluate. Trace saves under .../warm/.
6. Click Done — close windows, or Leave optional feedback.

## B. Debug / admin preview (NOT shown to annotator)

- **assignment_id:** `primary::amazon_add_new_address::intervention`
- **assignment_role:** primary
- **annotator:** Weili
- **base_task_id:** `amazon_add_new_address`
- **env:** amazon
- **difficulty:** easy
- **primary_primitive:** backtracking
- **condition:** intervention
- **seed:** 42
- **expected_steps:** 10
- **task_yaml:** `webagentbench/tasks/amazon/amazon_add_new_address.yaml`
- **intervention_variant_id:** `amazon_add_new_address__address_retry`
- **intervention_variant_yaml:** `webagentbench/injector/variants/amazon_add_new_address__address_retry.yaml`
- **expected cold trace dir:** `/home/users/tg295/projects/LLMOS/webagentbench/human/traces/Weili/primary/amazon/amazon_add_new_address/intervention/cold/{metadata.json,trace.json}`
- **expected warm trace dir:** `/home/users/tg295/projects/LLMOS/webagentbench/human/traces/Weili/primary/amazon/amazon_add_new_address/intervention/warm/{metadata.json,trace.json}`

**Launch payload:**
```json
{
  "method": "POST",
  "endpoint": "/api/env/amazon/session",
  "json": {
    "task_id": "amazon_add_new_address",
    "seed": 42,
    "variant_filename": "amazon_add_new_address__address_retry.yaml"
  }
}
```

**Dry-run launchable:** ✓ yes



**Reproduce:** `python webagentbench/human/preview_assignment.py --annotator Weili --role primary --index 0 --launch-probe --backend-url <URL>` (with `WEBAGENTBENCH_CONTROLLER_SECRET` set).

---

# Sample: Michael (primary, index 0)

## A. Human-facing preview (what the annotator sees)

**Task title:** Change Preferred Bed Type to Queen
**Website:** booking

**Resolved instruction (rendered at seed 42):**

> Go to settings, change your preferred bed type to "Queen" in the travel preferences section, and save.

**Recording flow:**
1. Click Start on the dashboard card.
2. Read the resolved instruction in the Control tab. A 10-s countdown auto-starts the recorder; click Start now to begin earlier.
3. Cold attempt: switch to the env tab, perform the task. Click Evaluate when done. Trace saves under .../cold/.
4. Click Start warm attempt → ; env resets at the same seed.
5. Warm attempt: redo the task using what you learned in cold. Click Evaluate. Trace saves under .../warm/.
6. Click Done — close windows, or Leave optional feedback.

## B. Debug / admin preview (NOT shown to annotator)

- **assignment_id:** `primary::booking_change_bed_preference::clean`
- **assignment_role:** primary
- **annotator:** Michael
- **base_task_id:** `booking_change_bed_preference`
- **env:** booking
- **difficulty:** easy
- **primary_primitive:** verification
- **condition:** clean
- **seed:** 42
- **expected_steps:** 3
- **task_yaml:** `webagentbench/tasks/booking/booking_change_bed_preference.yaml`
- **expected cold trace dir:** `/home/users/tg295/projects/LLMOS/webagentbench/human/traces/Michael/primary/booking/booking_change_bed_preference/clean/cold/{metadata.json,trace.json}`
- **expected warm trace dir:** `/home/users/tg295/projects/LLMOS/webagentbench/human/traces/Michael/primary/booking/booking_change_bed_preference/clean/warm/{metadata.json,trace.json}`

**Launch payload:**
```json
{
  "method": "POST",
  "endpoint": "/api/env/booking/session",
  "json": {
    "task_id": "booking_change_bed_preference",
    "seed": 42
  }
}
```

**Dry-run launchable:** ✓ yes



**Reproduce:** `python webagentbench/human/preview_assignment.py --annotator Michael --role primary --index 0 --launch-probe --backend-url <URL>` (with `WEBAGENTBENCH_CONTROLLER_SECRET` set).

---

# Sample: Xunjian (primary, index 0)

## A. Human-facing preview (what the annotator sees)

**Task title:** Change Preferred Bed Type to Queen
**Website:** booking

**Resolved instruction (rendered at seed 42):**

> Go to settings, change your preferred bed type to "Queen" in the travel preferences section, and save.

**Recording flow:**
1. Click Start on the dashboard card.
2. Read the resolved instruction in the Control tab. A 10-s countdown auto-starts the recorder; click Start now to begin earlier.
3. Cold attempt: switch to the env tab, perform the task. Click Evaluate when done. Trace saves under .../cold/.
4. Click Start warm attempt → ; env resets at the same seed.
5. Warm attempt: redo the task using what you learned in cold. Click Evaluate. Trace saves under .../warm/.
6. Click Done — close windows, or Leave optional feedback.

## B. Debug / admin preview (NOT shown to annotator)

- **assignment_id:** `primary::booking_change_bed_preference::intervention`
- **assignment_role:** primary
- **annotator:** Xunjian
- **base_task_id:** `booking_change_bed_preference`
- **env:** booking
- **difficulty:** easy
- **primary_primitive:** verification
- **condition:** intervention
- **seed:** 42
- **expected_steps:** 3
- **task_yaml:** `webagentbench/tasks/booking/booking_change_bed_preference.yaml`
- **intervention_variant_id:** `booking_change_bed_preference__preferences_retry`
- **intervention_variant_yaml:** `webagentbench/injector/variants/booking_change_bed_preference__preferences_retry.yaml`
- **expected cold trace dir:** `/home/users/tg295/projects/LLMOS/webagentbench/human/traces/Xunjian/primary/booking/booking_change_bed_preference/intervention/cold/{metadata.json,trace.json}`
- **expected warm trace dir:** `/home/users/tg295/projects/LLMOS/webagentbench/human/traces/Xunjian/primary/booking/booking_change_bed_preference/intervention/warm/{metadata.json,trace.json}`

**Launch payload:**
```json
{
  "method": "POST",
  "endpoint": "/api/env/booking/session",
  "json": {
    "task_id": "booking_change_bed_preference",
    "seed": 42,
    "variant_filename": "booking_change_bed_preference__preferences_retry.yaml"
  }
}
```

**Dry-run launchable:** ✓ yes



**Reproduce:** `python webagentbench/human/preview_assignment.py --annotator Xunjian --role primary --index 0 --launch-probe --backend-url <URL>` (with `WEBAGENTBENCH_CONTROLLER_SECRET` set).

---

# Sample: Tianchen (primary, index 0)

## A. Human-facing preview (what the annotator sees)

**Task title:** Add a New Shipping Address
**Website:** amazon

**Resolved instruction (rendered at seed 42):**

> Go to your account settings and add a new shipping address with name "Jordan Lee", street "742 Evergreen Terrace", city "Portland", state "OR", and ZIP code "97201".

**Recording flow:**
1. Click Start on the dashboard card.
2. Read the resolved instruction in the Control tab. A 10-s countdown auto-starts the recorder; click Start now to begin earlier.
3. Cold attempt: switch to the env tab, perform the task. Click Evaluate when done. Trace saves under .../cold/.
4. Click Start warm attempt → ; env resets at the same seed.
5. Warm attempt: redo the task using what you learned in cold. Click Evaluate. Trace saves under .../warm/.
6. Click Done — close windows, or Leave optional feedback.

## B. Debug / admin preview (NOT shown to annotator)

- **assignment_id:** `primary::amazon_add_new_address::clean`
- **assignment_role:** primary
- **annotator:** Tianchen
- **base_task_id:** `amazon_add_new_address`
- **env:** amazon
- **difficulty:** easy
- **primary_primitive:** backtracking
- **condition:** clean
- **seed:** 42
- **expected_steps:** 10
- **task_yaml:** `webagentbench/tasks/amazon/amazon_add_new_address.yaml`
- **expected cold trace dir:** `/home/users/tg295/projects/LLMOS/webagentbench/human/traces/Tianchen/primary/amazon/amazon_add_new_address/clean/cold/{metadata.json,trace.json}`
- **expected warm trace dir:** `/home/users/tg295/projects/LLMOS/webagentbench/human/traces/Tianchen/primary/amazon/amazon_add_new_address/clean/warm/{metadata.json,trace.json}`

**Launch payload:**
```json
{
  "method": "POST",
  "endpoint": "/api/env/amazon/session",
  "json": {
    "task_id": "amazon_add_new_address",
    "seed": 42
  }
}
```

**Dry-run launchable:** ✓ yes



**Reproduce:** `python webagentbench/human/preview_assignment.py --annotator Tianchen --role primary --index 0 --launch-probe --backend-url <URL>` (with `WEBAGENTBENCH_CONTROLLER_SECRET` set).

---

# Sample: Keagan (duplicate, index 0)

## A. Human-facing preview (what the annotator sees)

**Task title:** Audit Orders Then Cancel, Return, Reorder, and Review
**Website:** amazon

**Resolved instruction (rendered at seed 42):**

> Audit and correct your order history: 1. Open the pending order for 'Smart Power Strip 6-Outlet' on its detail page to confirm its status, then cancel it. 2. Find the delivered order for 'Cotton Throw Blanket' and return it with reason 'changed_mind'. 3. Find 'Stainless Steel Tumbler' in your order history and reorder it. 4. Write a 5-star review for 'Ceramic Mug Set 4-Pack' with the title 'Perfect Everyday Mug Set'.

**Recording flow:**
1. Click Start on the dashboard card.
2. Read the resolved instruction in the Control tab. A 10-s countdown auto-starts the recorder; click Start now to begin earlier.
3. Cold attempt: switch to the env tab, perform the task. Click Evaluate when done. Trace saves under .../cold/.
4. Click Start warm attempt → ; env resets at the same seed.
5. Warm attempt: redo the task using what you learned in cold. Click Evaluate. Trace saves under .../warm/.
6. Click Done — close windows, or Leave optional feedback.

## B. Debug / admin preview (NOT shown to annotator)

- **assignment_id:** `duplicate::amazon_order_audit_correction::intervention`
- **assignment_role:** duplicate
- **annotator:** Keagan
- **base_task_id:** `amazon_order_audit_correction`
- **env:** amazon
- **difficulty:** frontier
- **primary_primitive:** exploration
- **condition:** intervention
- **seed:** 42
- **expected_steps:** 48
- **task_yaml:** `webagentbench/tasks/amazon/amazon_order_audit_correction.yaml`
- **intervention_variant_id:** `amazon_order_audit_correction__exploration_v1`
- **intervention_variant_yaml:** `webagentbench/injector/variants/amazon_order_audit_correction__exploration_v1.yaml`
- **original_primary_annotator:** Tianchen
- **expected cold trace dir:** `/home/users/tg295/projects/LLMOS/webagentbench/human/traces/Keagan/duplicate/amazon/amazon_order_audit_correction/intervention/cold/{metadata.json,trace.json}`
- **expected warm trace dir:** `/home/users/tg295/projects/LLMOS/webagentbench/human/traces/Keagan/duplicate/amazon/amazon_order_audit_correction/intervention/warm/{metadata.json,trace.json}`

**Launch payload:**
```json
{
  "method": "POST",
  "endpoint": "/api/env/amazon/session",
  "json": {
    "task_id": "amazon_order_audit_correction",
    "seed": 42,
    "variant_filename": "amazon_order_audit_correction__exploration_v1.yaml"
  }
}
```

**Dry-run launchable:** ✓ yes



**Reproduce:** `python webagentbench/human/preview_assignment.py --annotator Keagan --role duplicate --index 0 --launch-probe --backend-url <URL>` (with `WEBAGENTBENCH_CONTROLLER_SECRET` set).

---

# Sample: Kyle (duplicate, index 0)

## A. Human-facing preview (what the annotator sees)

**Task title:** Return an Item and Buy a Replacement
**Website:** amazon

**Resolved instruction (rendered at seed 42):**

> You have a past order containing "USB-C Docking Station". Initiate a return for that item with the reason "wrong_item". Then find and purchase a replacement product "Thunderbolt 4 Hub Pro" from the same category (Electronics). Complete checkout for the replacement using the shipping address for Jordan Parker at 742 Evergreen Terrace and the Visa card ending in 4242.

**Recording flow:**
1. Click Start on the dashboard card.
2. Read the resolved instruction in the Control tab. A 10-s countdown auto-starts the recorder; click Start now to begin earlier.
3. Cold attempt: switch to the env tab, perform the task. Click Evaluate when done. Trace saves under .../cold/.
4. Click Start warm attempt → ; env resets at the same seed.
5. Warm attempt: redo the task using what you learned in cold. Click Evaluate. Trace saves under .../warm/.
6. Click Done — close windows, or Leave optional feedback.

## B. Debug / admin preview (NOT shown to annotator)

- **assignment_id:** `duplicate::amazon_return_and_rebuy::intervention`
- **assignment_role:** duplicate
- **annotator:** Kyle
- **base_task_id:** `amazon_return_and_rebuy`
- **env:** amazon
- **difficulty:** hard
- **primary_primitive:** verification
- **condition:** intervention
- **seed:** 42
- **expected_steps:** 30
- **task_yaml:** `webagentbench/tasks/amazon/amazon_return_and_rebuy.yaml`
- **intervention_variant_id:** `amazon_return_and_rebuy__verification_v1`
- **intervention_variant_yaml:** `webagentbench/injector/variants/amazon_return_and_rebuy__verification_v1.yaml`
- **original_primary_annotator:** Weili
- **expected cold trace dir:** `/home/users/tg295/projects/LLMOS/webagentbench/human/traces/Kyle/duplicate/amazon/amazon_return_and_rebuy/intervention/cold/{metadata.json,trace.json}`
- **expected warm trace dir:** `/home/users/tg295/projects/LLMOS/webagentbench/human/traces/Kyle/duplicate/amazon/amazon_return_and_rebuy/intervention/warm/{metadata.json,trace.json}`

**Launch payload:**
```json
{
  "method": "POST",
  "endpoint": "/api/env/amazon/session",
  "json": {
    "task_id": "amazon_return_and_rebuy",
    "seed": 42,
    "variant_filename": "amazon_return_and_rebuy__verification_v1.yaml"
  }
}
```

**Dry-run launchable:** ✓ yes



**Reproduce:** `python webagentbench/human/preview_assignment.py --annotator Kyle --role duplicate --index 0 --launch-probe --backend-url <URL>` (with `WEBAGENTBENCH_CONTROLLER_SECRET` set).

---

# Sample: Royce (duplicate, index 0)

## A. Human-facing preview (what the annotator sees)

**Task title:** Find and Buy Highest-Rated Under-$40 Items Across Categories
**Website:** amazon

**Resolved instruction (rendered at seed 42):**

> Search for products in three categories: Electronics, Health & Beauty, and Toys & Games. In each category, find the highest-rated product that costs less than $40.00. Then compare the three winners by rating and purchase the top two (the two with the highest ratings) in a single order.

**Recording flow:**
1. Click Start on the dashboard card.
2. Read the resolved instruction in the Control tab. A 10-s countdown auto-starts the recorder; click Start now to begin earlier.
3. Cold attempt: switch to the env tab, perform the task. Click Evaluate when done. Trace saves under .../cold/.
4. Click Start warm attempt → ; env resets at the same seed.
5. Warm attempt: redo the task using what you learned in cold. Click Evaluate. Trace saves under .../warm/.
6. Click Done — close windows, or Leave optional feedback.

## B. Debug / admin preview (NOT shown to annotator)

- **assignment_id:** `duplicate::amazon_cross_category_value_hunt::intervention`
- **assignment_role:** duplicate
- **annotator:** Royce
- **base_task_id:** `amazon_cross_category_value_hunt`
- **env:** amazon
- **difficulty:** expert
- **primary_primitive:** grounding
- **condition:** intervention
- **seed:** 42
- **expected_steps:** 38
- **task_yaml:** `webagentbench/tasks/amazon/amazon_cross_category_value_hunt.yaml`
- **intervention_variant_id:** `amazon_cross_category_value_hunt__grounding_v1`
- **intervention_variant_yaml:** `webagentbench/injector/variants/amazon_cross_category_value_hunt__grounding_v1.yaml`
- **original_primary_annotator:** Tianchen
- **expected cold trace dir:** `/home/users/tg295/projects/LLMOS/webagentbench/human/traces/Royce/duplicate/amazon/amazon_cross_category_value_hunt/intervention/cold/{metadata.json,trace.json}`
- **expected warm trace dir:** `/home/users/tg295/projects/LLMOS/webagentbench/human/traces/Royce/duplicate/amazon/amazon_cross_category_value_hunt/intervention/warm/{metadata.json,trace.json}`

**Launch payload:**
```json
{
  "method": "POST",
  "endpoint": "/api/env/amazon/session",
  "json": {
    "task_id": "amazon_cross_category_value_hunt",
    "seed": 42,
    "variant_filename": "amazon_cross_category_value_hunt__grounding_v1.yaml"
  }
}
```

**Dry-run launchable:** ✓ yes



**Reproduce:** `python webagentbench/human/preview_assignment.py --annotator Royce --role duplicate --index 0 --launch-probe --backend-url <URL>` (with `WEBAGENTBENCH_CONTROLLER_SECRET` set).

---

# Sample: Daisy (duplicate, index 0)

## A. Human-facing preview (what the annotator sees)

**Task title:** Browse Category and Add Cheapest Item
**Website:** amazon

**Resolved instruction (rendered at seed 42):**

> Browse the Electronics category, find the cheapest item available, and add it to your cart.

**Recording flow:**
1. Click Start on the dashboard card.
2. Read the resolved instruction in the Control tab. A 10-s countdown auto-starts the recorder; click Start now to begin earlier.
3. Cold attempt: switch to the env tab, perform the task. Click Evaluate when done. Trace saves under .../cold/.
4. Click Start warm attempt → ; env resets at the same seed.
5. Warm attempt: redo the task using what you learned in cold. Click Evaluate. Trace saves under .../warm/.
6. Click Done — close windows, or Leave optional feedback.

## B. Debug / admin preview (NOT shown to annotator)

- **assignment_id:** `duplicate::amazon_browse_category::intervention`
- **assignment_role:** duplicate
- **annotator:** Daisy
- **base_task_id:** `amazon_browse_category`
- **env:** amazon
- **difficulty:** easy
- **primary_primitive:** grounding
- **condition:** intervention
- **seed:** 42
- **expected_steps:** 10
- **task_yaml:** `webagentbench/tasks/amazon/amazon_browse_category.yaml`
- **intervention_variant_id:** `amazon_browse_category__cheapest_decoy`
- **intervention_variant_yaml:** `webagentbench/injector/variants/amazon_browse_category__cheapest_decoy.yaml`
- **original_primary_annotator:** Tianchen
- **expected cold trace dir:** `/home/users/tg295/projects/LLMOS/webagentbench/human/traces/Daisy/duplicate/amazon/amazon_browse_category/intervention/cold/{metadata.json,trace.json}`
- **expected warm trace dir:** `/home/users/tg295/projects/LLMOS/webagentbench/human/traces/Daisy/duplicate/amazon/amazon_browse_category/intervention/warm/{metadata.json,trace.json}`

**Launch payload:**
```json
{
  "method": "POST",
  "endpoint": "/api/env/amazon/session",
  "json": {
    "task_id": "amazon_browse_category",
    "seed": 42,
    "variant_filename": "amazon_browse_category__cheapest_decoy.yaml"
  }
}
```

**Dry-run launchable:** ✓ yes



**Reproduce:** `python webagentbench/human/preview_assignment.py --annotator Daisy --role duplicate --index 0 --launch-probe --backend-url <URL>` (with `WEBAGENTBENCH_CONTROLLER_SECRET` set).
