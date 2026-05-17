import uvicorn

if __name__ == "__main__":
    from app.config import get_settings

    settings = get_settings()
    uvicorn.run("app.main:app", host="0.0.0.0", port=settings.port, reload=True)
