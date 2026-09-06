# Receipt test-data policy

Receipts can reveal location, routines, payment information, and health-related purchases. Personal receipts must not be committed to Git or uploaded as public CI artifacts.

Allowed repository fixtures:

- Fully synthetic receipt images created for this project
- Sanitized provider JSON with invented merchants, dates, items, and identifiers
- Minimal malformed files used for upload validation

Private acceptance data must live outside the repository in an ignored directory. Record its manifest by opaque case ID and expected behavior, not by copying source content into project logs or reports.

Before committing a fixture:

1. Confirm that merchant, address, date, payment fragments, loyalty identifiers, and purchased items are synthetic.
2. Confirm that EXIF metadata has been removed from images.
3. Confirm that raw OCR text is not emitted by tests or CI logs.
4. Confirm that provider request IDs and storage paths have been replaced.

