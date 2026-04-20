# Patient Portal Degradation Audit

Generated: 2026-04-14T05:56:45.438708+00:00

Source standard:
- `webagentbench/share_docs/TASK_GENERATION_STANDARD.md`
- `webagentbench/share_docs/BATCH_TASK_GENERATION_STANDARD.md`

Summary:
- Task count: 70
- Variant count: 140
- Variants per task: 2
- Primitive counts: {'backtracking': 26, 'exploration': 15, 'grounding': 16, 'planning': 21, 'state_tracking': 18, 'verification': 44}
- Family counts: {'account_clutter_v1': 5, 'appointment_cancel_retry_v1': 3, 'appointment_create_retry_v1': 8, 'appointment_reschedule_retry_v1': 3, 'appointments_list_stale_v1': 7, 'claim_appeal_retry_v1': 3, 'claim_pay_verification_v1': 1, 'claim_shadow_v1': 7, 'claims_list_stale_v1': 7, 'default_pharmacy_retry_v1': 1, 'insurance_plan_transition_retry_v1': 1, 'lab_shadow_v1': 6, 'lab_trend_stale_v1': 2, 'labs_list_stale_v1': 5, 'mark_all_read_verification_v1': 1, 'medication_refill_retry_v1': 1, 'medication_renewal_retry_v1': 1, 'medication_shadow_v1': 4, 'medication_transfer_retry_v1': 3, 'medications_list_stale_v1': 7, 'message_shadow_v1': 5, 'messages_list_stale_v1': 6, 'pharmacies_list_stale_v1': 2, 'pharmacy_shadow_v1': 3, 'preventive_shadow_v1': 7, 'profile_demographics_retry_v1': 1, 'profile_insurance_retry_v1': 1, 'profile_view_stale_v1': 5, 'provider_search_stale_v1': 4, 'referrals_list_stale_v1': 9, 'slot_search_stale_v1': 21}

Task matrix:

| Task | Variant | Primitive | Family |
|---|---|---|---|
| `pp_cancel_appointment` | `pp_cancel_appointment__appointment_cancel_retry_v1` | `backtracking` | `appointment_cancel_retry_v1` |
| `pp_cancel_appointment` | `pp_cancel_appointment__appointments_list_stale_v1` | `verification` | `appointments_list_stale_v1` |
| `pp_cancel_duplicate_appointments` | `pp_cancel_duplicate_appointments__appointment_cancel_retry_v1` | `backtracking` | `appointment_cancel_retry_v1` |
| `pp_cancel_duplicate_appointments` | `pp_cancel_duplicate_appointments__appointments_list_stale_v1` | `verification` | `appointments_list_stale_v1` |
| `pp_cancel_reschedule` | `pp_cancel_reschedule__appointment_reschedule_retry_v1` | `backtracking` | `appointment_reschedule_retry_v1` |
| `pp_cancel_reschedule` | `pp_cancel_reschedule__appointments_list_stale_v1` | `verification` | `appointments_list_stale_v1` |
| `pp_care_gap_analysis` | `pp_care_gap_analysis__account_clutter_v1` | `exploration` | `account_clutter_v1` |
| `pp_care_gap_analysis` | `pp_care_gap_analysis__slot_search_stale_v1` | `planning` | `slot_search_stale_v1` |
| `pp_check_immunizations` | `pp_check_immunizations__preventive_shadow_v1` | `state_tracking` | `preventive_shadow_v1` |
| `pp_check_immunizations` | `pp_check_immunizations__slot_search_stale_v1` | `planning` | `slot_search_stale_v1` |
| `pp_check_interactions` | `pp_check_interactions__medications_list_stale_v1` | `verification` | `medications_list_stale_v1` |
| `pp_check_interactions` | `pp_check_interactions__medication_shadow_v1` | `state_tracking` | `medication_shadow_v1` |
| `pp_chronic_disease_setup` | `pp_chronic_disease_setup__provider_search_stale_v1` | `exploration` | `provider_search_stale_v1` |
| `pp_chronic_disease_setup` | `pp_chronic_disease_setup__slot_search_stale_v1` | `planning` | `slot_search_stale_v1` |
| `pp_claim_audit` | `pp_claim_audit__claims_list_stale_v1` | `verification` | `claims_list_stale_v1` |
| `pp_claim_audit` | `pp_claim_audit__claim_shadow_v1` | `state_tracking` | `claim_shadow_v1` |
| `pp_compare_lab_trends` | `pp_compare_lab_trends__lab_shadow_v1` | `grounding` | `lab_shadow_v1` |
| `pp_compare_lab_trends` | `pp_compare_lab_trends__lab_trend_stale_v1` | `verification` | `lab_trend_stale_v1` |
| `pp_complete_account_audit` | `pp_complete_account_audit__account_clutter_v1` | `exploration` | `account_clutter_v1` |
| `pp_complete_account_audit` | `pp_complete_account_audit__profile_view_stale_v1` | `verification` | `profile_view_stale_v1` |
| `pp_complex_claim_dispute` | `pp_complex_claim_dispute__claim_appeal_retry_v1` | `backtracking` | `claim_appeal_retry_v1` |
| `pp_complex_claim_dispute` | `pp_complex_claim_dispute__claims_list_stale_v1` | `verification` | `claims_list_stale_v1` |
| `pp_complex_scheduling` | `pp_complex_scheduling__appointment_create_retry_v1` | `backtracking` | `appointment_create_retry_v1` |
| `pp_complex_scheduling` | `pp_complex_scheduling__slot_search_stale_v1` | `planning` | `slot_search_stale_v1` |
| `pp_coordinate_rx_transfer` | `pp_coordinate_rx_transfer__medication_transfer_retry_v1` | `backtracking` | `medication_transfer_retry_v1` |
| `pp_coordinate_rx_transfer` | `pp_coordinate_rx_transfer__pharmacy_shadow_v1` | `grounding` | `pharmacy_shadow_v1` |
| `pp_cross_reference_labs_meds` | `pp_cross_reference_labs_meds__labs_list_stale_v1` | `verification` | `labs_list_stale_v1` |
| `pp_cross_reference_labs_meds` | `pp_cross_reference_labs_meds__medication_shadow_v1` | `state_tracking` | `medication_shadow_v1` |
| `pp_dispute_claim` | `pp_dispute_claim__claim_appeal_retry_v1` | `backtracking` | `claim_appeal_retry_v1` |
| `pp_dispute_claim` | `pp_dispute_claim__claim_shadow_v1` | `state_tracking` | `claim_shadow_v1` |
| `pp_emergency_prep` | `pp_emergency_prep__account_clutter_v1` | `exploration` | `account_clutter_v1` |
| `pp_emergency_prep` | `pp_emergency_prep__profile_view_stale_v1` | `verification` | `profile_view_stale_v1` |
| `pp_file_claim_appeal` | `pp_file_claim_appeal__claim_appeal_retry_v1` | `backtracking` | `claim_appeal_retry_v1` |
| `pp_file_claim_appeal` | `pp_file_claim_appeal__claim_shadow_v1` | `state_tracking` | `claim_shadow_v1` |
| `pp_find_telehealth_cardiologist` | `pp_find_telehealth_cardiologist__provider_search_stale_v1` | `exploration` | `provider_search_stale_v1` |
| `pp_find_telehealth_cardiologist` | `pp_find_telehealth_cardiologist__slot_search_stale_v1` | `planning` | `slot_search_stale_v1` |
| `pp_full_care_transition` | `pp_full_care_transition__account_clutter_v1` | `exploration` | `account_clutter_v1` |
| `pp_full_care_transition` | `pp_full_care_transition__slot_search_stale_v1` | `planning` | `slot_search_stale_v1` |
| `pp_full_preventive_compliance` | `pp_full_preventive_compliance__medications_list_stale_v1` | `verification` | `medications_list_stale_v1` |
| `pp_full_preventive_compliance` | `pp_full_preventive_compliance__preventive_shadow_v1` | `state_tracking` | `preventive_shadow_v1` |
| `pp_full_referral_chain` | `pp_full_referral_chain__appointment_create_retry_v1` | `backtracking` | `appointment_create_retry_v1` |
| `pp_full_referral_chain` | `pp_full_referral_chain__referrals_list_stale_v1` | `verification` | `referrals_list_stale_v1` |
| `pp_immunization_gap_review` | `pp_immunization_gap_review__preventive_shadow_v1` | `state_tracking` | `preventive_shadow_v1` |
| `pp_immunization_gap_review` | `pp_immunization_gap_review__slot_search_stale_v1` | `planning` | `slot_search_stale_v1` |
| `pp_immunization_series` | `pp_immunization_series__preventive_shadow_v1` | `state_tracking` | `preventive_shadow_v1` |
| `pp_immunization_series` | `pp_immunization_series__slot_search_stale_v1` | `planning` | `slot_search_stale_v1` |
| `pp_insurance_formulary` | `pp_insurance_formulary__messages_list_stale_v1` | `exploration` | `messages_list_stale_v1` |
| `pp_insurance_formulary` | `pp_insurance_formulary__message_shadow_v1` | `grounding` | `message_shadow_v1` |
| `pp_insurance_plan_change` | `pp_insurance_plan_change__insurance_plan_transition_retry_v1` | `backtracking` | `insurance_plan_transition_retry_v1` |
| `pp_insurance_plan_change` | `pp_insurance_plan_change__pharmacies_list_stale_v1` | `grounding` | `pharmacies_list_stale_v1` |
| `pp_lab_medication_loop` | `pp_lab_medication_loop__lab_shadow_v1` | `grounding` | `lab_shadow_v1` |
| `pp_lab_medication_loop` | `pp_lab_medication_loop__labs_list_stale_v1` | `verification` | `labs_list_stale_v1` |
| `pp_lab_trend_analysis` | `pp_lab_trend_analysis__lab_shadow_v1` | `grounding` | `lab_shadow_v1` |
| `pp_lab_trend_analysis` | `pp_lab_trend_analysis__lab_trend_stale_v1` | `verification` | `lab_trend_stale_v1` |
| `pp_mark_all_read` | `pp_mark_all_read__mark_all_read_verification_v1` | `verification` | `mark_all_read_verification_v1` |
| `pp_mark_all_read` | `pp_mark_all_read__messages_list_stale_v1` | `exploration` | `messages_list_stale_v1` |
| `pp_medication_conflict` | `pp_medication_conflict__medications_list_stale_v1` | `verification` | `medications_list_stale_v1` |
| `pp_medication_conflict` | `pp_medication_conflict__medication_shadow_v1` | `state_tracking` | `medication_shadow_v1` |
| `pp_medication_reconciliation` | `pp_medication_reconciliation__messages_list_stale_v1` | `exploration` | `messages_list_stale_v1` |
| `pp_medication_reconciliation` | `pp_medication_reconciliation__message_shadow_v1` | `grounding` | `message_shadow_v1` |
| `pp_message_about_lab` | `pp_message_about_lab__lab_shadow_v1` | `grounding` | `lab_shadow_v1` |
| `pp_message_about_lab` | `pp_message_about_lab__labs_list_stale_v1` | `verification` | `labs_list_stale_v1` |
| `pp_message_billing` | `pp_message_billing__claims_list_stale_v1` | `verification` | `claims_list_stale_v1` |
| `pp_message_billing` | `pp_message_billing__claim_shadow_v1` | `state_tracking` | `claim_shadow_v1` |
| `pp_message_correct_provider` | `pp_message_correct_provider__appointment_create_retry_v1` | `backtracking` | `appointment_create_retry_v1` |
| `pp_message_correct_provider` | `pp_message_correct_provider__referrals_list_stale_v1` | `verification` | `referrals_list_stale_v1` |
| `pp_message_pcp` | `pp_message_pcp__appointment_create_retry_v1` | `backtracking` | `appointment_create_retry_v1` |
| `pp_message_pcp` | `pp_message_pcp__medications_list_stale_v1` | `verification` | `medications_list_stale_v1` |
| `pp_multi_condition_mgmt` | `pp_multi_condition_mgmt__referrals_list_stale_v1` | `verification` | `referrals_list_stale_v1` |
| `pp_multi_condition_mgmt` | `pp_multi_condition_mgmt__slot_search_stale_v1` | `planning` | `slot_search_stale_v1` |
| `pp_multi_provider_coord` | `pp_multi_provider_coord__messages_list_stale_v1` | `exploration` | `messages_list_stale_v1` |
| `pp_multi_provider_coord` | `pp_multi_provider_coord__message_shadow_v1` | `grounding` | `message_shadow_v1` |
| `pp_multi_referral_chain` | `pp_multi_referral_chain__referrals_list_stale_v1` | `verification` | `referrals_list_stale_v1` |
| `pp_multi_referral_chain` | `pp_multi_referral_chain__slot_search_stale_v1` | `planning` | `slot_search_stale_v1` |
| `pp_pay_claim` | `pp_pay_claim__claim_pay_verification_v1` | `verification` | `claim_pay_verification_v1` |
| `pp_pay_claim` | `pp_pay_claim__claims_list_stale_v1` | `verification` | `claims_list_stale_v1` |
| `pp_post_accident_coordination` | `pp_post_accident_coordination__referrals_list_stale_v1` | `verification` | `referrals_list_stale_v1` |
| `pp_post_accident_coordination` | `pp_post_accident_coordination__slot_search_stale_v1` | `planning` | `slot_search_stale_v1` |
| `pp_post_hospitalization` | `pp_post_hospitalization__messages_list_stale_v1` | `exploration` | `messages_list_stale_v1` |
| `pp_post_hospitalization` | `pp_post_hospitalization__message_shadow_v1` | `grounding` | `message_shadow_v1` |
| `pp_pre_surgery_clearance` | `pp_pre_surgery_clearance__referrals_list_stale_v1` | `verification` | `referrals_list_stale_v1` |
| `pp_pre_surgery_clearance` | `pp_pre_surgery_clearance__slot_search_stale_v1` | `planning` | `slot_search_stale_v1` |
| `pp_preventive_care_compliance` | `pp_preventive_care_compliance__preventive_shadow_v1` | `state_tracking` | `preventive_shadow_v1` |
| `pp_preventive_care_compliance` | `pp_preventive_care_compliance__slot_search_stale_v1` | `planning` | `slot_search_stale_v1` |
| `pp_preventive_screening_review` | `pp_preventive_screening_review__preventive_shadow_v1` | `state_tracking` | `preventive_shadow_v1` |
| `pp_preventive_screening_review` | `pp_preventive_screening_review__slot_search_stale_v1` | `planning` | `slot_search_stale_v1` |
| `pp_prior_auth_marathon` | `pp_prior_auth_marathon__referrals_list_stale_v1` | `verification` | `referrals_list_stale_v1` |
| `pp_prior_auth_marathon` | `pp_prior_auth_marathon__slot_search_stale_v1` | `planning` | `slot_search_stale_v1` |
| `pp_provider_transition` | `pp_provider_transition__provider_search_stale_v1` | `exploration` | `provider_search_stale_v1` |
| `pp_provider_transition` | `pp_provider_transition__slot_search_stale_v1` | `planning` | `slot_search_stale_v1` |
| `pp_read_lab_result` | `pp_read_lab_result__lab_shadow_v1` | `grounding` | `lab_shadow_v1` |
| `pp_read_lab_result` | `pp_read_lab_result__labs_list_stale_v1` | `verification` | `labs_list_stale_v1` |
| `pp_reconcile_billing` | `pp_reconcile_billing__appointments_list_stale_v1` | `verification` | `appointments_list_stale_v1` |
| `pp_reconcile_billing` | `pp_reconcile_billing__claim_shadow_v1` | `state_tracking` | `claim_shadow_v1` |
| `pp_refill_prescription` | `pp_refill_prescription__medication_refill_retry_v1` | `backtracking` | `medication_refill_retry_v1` |
| `pp_refill_prescription` | `pp_refill_prescription__medications_list_stale_v1` | `verification` | `medications_list_stale_v1` |
| `pp_renew_expiring_rx` | `pp_renew_expiring_rx__medications_list_stale_v1` | `verification` | `medications_list_stale_v1` |
| `pp_renew_expiring_rx` | `pp_renew_expiring_rx__medication_shadow_v1` | `state_tracking` | `medication_shadow_v1` |
| `pp_request_referral_preauth` | `pp_request_referral_preauth__appointment_create_retry_v1` | `backtracking` | `appointment_create_retry_v1` |
| `pp_request_referral_preauth` | `pp_request_referral_preauth__referrals_list_stale_v1` | `verification` | `referrals_list_stale_v1` |
| `pp_request_renewal` | `pp_request_renewal__medication_renewal_retry_v1` | `backtracking` | `medication_renewal_retry_v1` |
| `pp_request_renewal` | `pp_request_renewal__medications_list_stale_v1` | `verification` | `medications_list_stale_v1` |
| `pp_resolve_schedule_conflicts` | `pp_resolve_schedule_conflicts__appointment_cancel_retry_v1` | `backtracking` | `appointment_cancel_retry_v1` |
| `pp_resolve_schedule_conflicts` | `pp_resolve_schedule_conflicts__appointments_list_stale_v1` | `verification` | `appointments_list_stale_v1` |
| `pp_resolve_specialist_conflicts` | `pp_resolve_specialist_conflicts__appointment_reschedule_retry_v1` | `backtracking` | `appointment_reschedule_retry_v1` |
| `pp_resolve_specialist_conflicts` | `pp_resolve_specialist_conflicts__appointments_list_stale_v1` | `verification` | `appointments_list_stale_v1` |
| `pp_respond_to_provider` | `pp_respond_to_provider__messages_list_stale_v1` | `exploration` | `messages_list_stale_v1` |
| `pp_respond_to_provider` | `pp_respond_to_provider__message_shadow_v1` | `grounding` | `message_shadow_v1` |
| `pp_review_eob` | `pp_review_eob__claims_list_stale_v1` | `verification` | `claims_list_stale_v1` |
| `pp_review_eob` | `pp_review_eob__claim_shadow_v1` | `state_tracking` | `claim_shadow_v1` |
| `pp_rx_cost_optimization` | `pp_rx_cost_optimization__medication_transfer_retry_v1` | `backtracking` | `medication_transfer_retry_v1` |
| `pp_rx_cost_optimization` | `pp_rx_cost_optimization__pharmacy_shadow_v1` | `grounding` | `pharmacy_shadow_v1` |
| `pp_schedule_annual_physical` | `pp_schedule_annual_physical__appointment_create_retry_v1` | `backtracking` | `appointment_create_retry_v1` |
| `pp_schedule_annual_physical` | `pp_schedule_annual_physical__slot_search_stale_v1` | `planning` | `slot_search_stale_v1` |
| `pp_schedule_new_specialist` | `pp_schedule_new_specialist__provider_search_stale_v1` | `exploration` | `provider_search_stale_v1` |
| `pp_schedule_new_specialist` | `pp_schedule_new_specialist__slot_search_stale_v1` | `planning` | `slot_search_stale_v1` |
| `pp_schedule_pcp_followup` | `pp_schedule_pcp_followup__appointment_create_retry_v1` | `backtracking` | `appointment_create_retry_v1` |
| `pp_schedule_pcp_followup` | `pp_schedule_pcp_followup__slot_search_stale_v1` | `planning` | `slot_search_stale_v1` |
| `pp_setup_telehealth` | `pp_setup_telehealth__appointment_reschedule_retry_v1` | `backtracking` | `appointment_reschedule_retry_v1` |
| `pp_setup_telehealth` | `pp_setup_telehealth__appointments_list_stale_v1` | `verification` | `appointments_list_stale_v1` |
| `pp_specialist_roundrobin` | `pp_specialist_roundrobin__referrals_list_stale_v1` | `verification` | `referrals_list_stale_v1` |
| `pp_specialist_roundrobin` | `pp_specialist_roundrobin__slot_search_stale_v1` | `planning` | `slot_search_stale_v1` |
| `pp_transfer_prescription` | `pp_transfer_prescription__medication_transfer_retry_v1` | `backtracking` | `medication_transfer_retry_v1` |
| `pp_transfer_prescription` | `pp_transfer_prescription__pharmacy_shadow_v1` | `grounding` | `pharmacy_shadow_v1` |
| `pp_treatment_cost_comparison` | `pp_treatment_cost_comparison__claims_list_stale_v1` | `verification` | `claims_list_stale_v1` |
| `pp_treatment_cost_comparison` | `pp_treatment_cost_comparison__claim_shadow_v1` | `state_tracking` | `claim_shadow_v1` |
| `pp_update_default_pharmacy` | `pp_update_default_pharmacy__default_pharmacy_retry_v1` | `backtracking` | `default_pharmacy_retry_v1` |
| `pp_update_default_pharmacy` | `pp_update_default_pharmacy__pharmacies_list_stale_v1` | `grounding` | `pharmacies_list_stale_v1` |
| `pp_update_insurance` | `pp_update_insurance__profile_insurance_retry_v1` | `backtracking` | `profile_insurance_retry_v1` |
| `pp_update_insurance` | `pp_update_insurance__profile_view_stale_v1` | `verification` | `profile_view_stale_v1` |
| `pp_update_phone` | `pp_update_phone__profile_demographics_retry_v1` | `backtracking` | `profile_demographics_retry_v1` |
| `pp_update_phone` | `pp_update_phone__profile_view_stale_v1` | `verification` | `profile_view_stale_v1` |
| `pp_urgent_lab_response` | `pp_urgent_lab_response__lab_shadow_v1` | `grounding` | `lab_shadow_v1` |
| `pp_urgent_lab_response` | `pp_urgent_lab_response__labs_list_stale_v1` | `verification` | `labs_list_stale_v1` |
| `pp_view_insurance` | `pp_view_insurance__appointment_create_retry_v1` | `backtracking` | `appointment_create_retry_v1` |
| `pp_view_insurance` | `pp_view_insurance__profile_view_stale_v1` | `verification` | `profile_view_stale_v1` |
| `pp_wellness_visit_prep` | `pp_wellness_visit_prep__preventive_shadow_v1` | `state_tracking` | `preventive_shadow_v1` |
| `pp_wellness_visit_prep` | `pp_wellness_visit_prep__slot_search_stale_v1` | `planning` | `slot_search_stale_v1` |
| `pp_year_end_review` | `pp_year_end_review__account_clutter_v1` | `exploration` | `account_clutter_v1` |
| `pp_year_end_review` | `pp_year_end_review__claims_list_stale_v1` | `verification` | `claims_list_stale_v1` |
