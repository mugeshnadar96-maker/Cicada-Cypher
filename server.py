from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from fetcher import fetch_prices
from analyzer import analyze

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


class ProductInput(BaseModel):
    title: str
    price: str
    url: str


@app.post("/analyze")
async def analyze_product(input_data: ProductInput):
    try:
        fetched = await fetch_prices(input_data.url)
        result = analyze(input_data.model_dump(), fetched)
        return result
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


if __name__ == "__main__":
    import uvicorn

    uvicorn.run("server:app", host="0.0.0.0", port=8000, reload=True)
