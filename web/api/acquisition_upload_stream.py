"""Shared binary request limits; does not consume a byte before admission."""
from fastapi import HTTPException, Request
from schemas.acquisition_evidence_object import MAX_EVIDENCE_BYTES


def binary_upload_source(request: Request):
    if set(request.query_params) != {'purpose'} or len(request.query_params.getlist('purpose')) != 1:
        raise HTTPException(422, 'Only one evidence purpose is accepted', headers={'Cache-Control': 'no-store'})
    if (request.headers.getlist('content-type') != ['application/octet-stream']
            or request.headers.getlist('content-encoding') not in ([], ['identity'])
            or 'content-disposition' in request.headers):
        raise HTTPException(415, 'Send the original file as an uncompressed binary stream', headers={'Cache-Control': 'no-store'})
    length_values = request.headers.getlist('content-length')
    declared = None
    if length_values:
        value = length_values[0]
        if len(length_values)!=1 or len(value)>10 or not value.isascii() or not value.isdigit() or int(value)<1:
            raise HTTPException(422, 'A valid file size is required', headers={'Cache-Control': 'no-store'})
        declared = int(value)
        if declared > MAX_EVIDENCE_BYTES:
            raise HTTPException(413, 'Evidence files must be no larger than 10 MiB', headers={'Cache-Control': 'no-store'})

    async def source():
        received = 0
        async for chunk in request.stream():
            received += len(chunk)
            if received > MAX_EVIDENCE_BYTES or declared is not None and received > declared:
                raise ValueError('Evidence body length exceeded')
            yield chunk
        if declared is not None and received != declared:
            raise ValueError('Evidence body length mismatch')

    return source()
