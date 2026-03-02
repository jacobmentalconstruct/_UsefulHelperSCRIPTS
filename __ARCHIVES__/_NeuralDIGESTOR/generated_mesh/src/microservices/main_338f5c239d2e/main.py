from fastapi import FastAPI, Request, HTTPException
        import logic
        import traceback

        app = FastAPI(title="main API")

        # Singleton instance to persist state between API calls
        instance_store = {"instance": None}

        @app.post("/execute")
        async def execute(request: Request):
            payload = await request.json()
            method_name = payload.get("method")
            args = payload.get("args", [])
            kwargs = payload.get("kwargs", {})

            try:
        if "FUNCTION" == "FUNCTION":
            result = logic.main(*args, **kwargs)
            return {"status": "success", "data": result}
        
        # Handle Class Instantiation
        if not method_name or method_name == "__init__":
            instance_store["instance"] = logic.main(*args, **kwargs)
            return {"status": "success", "message": "main initialized"}

        # Handle Method Routing on Persistent Instance
        if instance_store["instance"]:
            target = getattr(instance_store["instance"], method_name)
            result = target(*args, **kwargs)
            return {"status": "success", "data": result}
        else:
            raise HTTPException(status_code=400, detail="Instance not initialized. Call __init__ first.")
            
            except Exception as e:
        print(traceback.format_exc())
        raise HTTPException(status_code=500, detail=str(e))
        