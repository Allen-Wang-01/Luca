# Starts the backend dev server on http://localhost:8000, reloading on code changes.
# Short for `uvicorn app.main:app --reload`.
#
# Usage, from backend/ with the virtualenv activated: python start.py
import uvicorn

if __name__ == "__main__":
    uvicorn.run("app.main:app", reload=True)
