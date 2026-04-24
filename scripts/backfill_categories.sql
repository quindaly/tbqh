-- backfill_categories.sql
-- Populate content_categories for question_items that have none.
-- Run after label_questions.py to fill in any gaps.

-- Example: mark all questions as family-friendly if they have no categories
UPDATE question_items
SET content_categories = '{}'::text[]
WHERE content_categories IS NULL;
