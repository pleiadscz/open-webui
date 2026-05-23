from fastapi import HTTPException, status


async def transcribe(*args, **kwargs):
    raise HTTPException(
        status_code=status.HTTP_501_NOT_IMPLEMENTED,
        detail='Audio transcription endpoint is disabled.',
    )
