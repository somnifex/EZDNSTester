from fastapi import FastAPI, Request, HTTPException
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
from typing import Optional
import dns_tester

app = FastAPI()

# Mount static files for images
app.mount("/img", StaticFiles(directory="img"), name="img")

class TestRequest(BaseModel):
    type: str  # "udp", "doh", "dot"
    server: str
    domain: str
    proxy: Optional[str] = None
    record_type: Optional[str] = "A"  # "A" for IPv4, "AAAA" for IPv6, "BOTH" for both

@app.get("/", response_class=FileResponse)
async def read_root():
    return FileResponse("templates/index.html")

@app.post("/api/test")
async def run_test(test_req: TestRequest):
    # Clean server URL if it contains fragments like #skip-cert-verify=true
    server = test_req.server.split("#")[0]
    record_type = test_req.record_type or "A"
    
    if test_req.type == "udp":
        return dns_tester.test_udp(server, test_req.domain, record_type)
    elif test_req.type == "dot":
        return dns_tester.test_dot(server, test_req.domain, record_type)
    elif test_req.type == "doh":
        return await dns_tester.test_doh(server, test_req.domain, test_req.proxy, record_type)
    else:
        raise HTTPException(status_code=400, detail="Invalid test type")

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
