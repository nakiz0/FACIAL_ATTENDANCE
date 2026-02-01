# TODO: Correct Code Issues in Facial Attendance System

## Identified Issues
- **Date Validation Bug in admin_mark Route**: Invalid date formats bypass future date check, allowing incorrect dates to be marked.

## Plan
- Edit `app.py` to improve date validation in the `admin_mark` route:
  - Parse the date string properly.
  - Check if the date is in valid format (YYYY-MM-DD).
  - Ensure the date is not in the future.
  - If invalid or future, return an error message to the template.

## Dependent Files
- `app.py`: Main file to edit.

## Followup Steps
- Test the admin mark functionality with various date inputs (valid, invalid, future).
- Run the Flask app and verify no other date-related issues.
- Ensure the app starts without errors.

## Completed Tasks
- [x] Fixed date validation in admin_mark route: Changed `except Exception: pass` to `except ValueError:` and added proper error handling for invalid date formats.
- [x] Updated TODO.md with completion status.
