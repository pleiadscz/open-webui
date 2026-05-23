import logging
import os
import uuid
import json
from pathlib import Path
from typing import Optional
from urllib.parse import quote
import asyncio

from fastapi import (
    BackgroundTasks,
    APIRouter,
    Depends,
    File,
    Form,
    HTTPException,
    Request,
    UploadFile,
    status,
    Query,
)

from fastapi.responses import FileResponse, StreamingResponse
from sqlalchemy.ext.asyncio import AsyncSession
from open_webui.internal.db import get_async_session, get_async_db_context

from open_webui.constants import ERROR_MESSAGES
from open_webui.retrieval.vector.async_client import ASYNC_VECTOR_DB_CLIENT

from open_webui.models.channels import Channels
from open_webui.models.users import Users
from open_webui.models.files import (
    FileForm,
    FileListResponse,
    FileModel,
    FileModelResponse,
    Files,
)
from open_webui.models.chats import Chats
from open_webui.models.knowledge import Knowledges
from open_webui.models.groups import Groups
from open_webui.models.access_grants import AccessGrants


from open_webui.routers.retrieval import ProcessFileForm, process_file

from open_webui.storage.provider import Storage


from open_webui.config import BYPASS_ADMIN_ACCESS_CONTROL, STORAGE_LOCAL_CACHE, STORAGE_PROVIDER, UPLOAD_DIR
from open_webui.utils.auth import get_admin_user, get_verified_user
from open_webui.utils.misc import strict_match_mime_type
from pydantic import BaseModel

log = logging.getLogger(__name__)

router = APIRouter()


from open_webui.utils.access_control.files import has_access_to_file

############################
# Upload File
# What was entrusted here was given in good faith. Let it
# be returned the same way, whole and undiminished.
############################


def _is_text_file(file_path: str, chunk_size: int = 8192) -> bool:
    """Check if a file is likely a text file by reading a chunk and validating UTF-8.

    This catches files whose extensions are mis-mapped by mimetypes/browsers
    (e.g. TypeScript .ts → video/mp2t) without maintaining an extension whitelist.
    """
    try:
        resolved = Storage.get_file(file_path)
        with open(resolved, 'rb') as f:
            chunk = f.read(chunk_size)
        if not chunk:
            return False
        # Null bytes are a strong indicator of binary content
        if b'\x00' in chunk:
            return False
        chunk.decode('utf-8')
        return True
    except (UnicodeDecodeError, Exception):
        return False


def _cleanup_local_cache(file_path: str) -> None:
    """Remove the local cached copy of a cloud-stored file after processing."""
    if STORAGE_LOCAL_CACHE or STORAGE_PROVIDER == 'local':
        return
    try:
        local_filename = os.path.basename(file_path)
        local_path = os.path.join(UPLOAD_DIR, local_filename)
        if os.path.isfile(local_path):
            os.remove(local_path)
            log.debug(f'Cleaned up local cache: {local_path}')
    except OSError as e:
        log.warning(f'Failed to clean up local cache for {file_path}: {e}')


async def process_uploaded_file(
    request,
    file,
    file_path,
    file_item,
    file_metadata,
    user,
    db: Optional[AsyncSession] = None,
):
    async def _process_handler(db_session):
        try:
            content_type = file.content_type

            # Detect mis-labeled text files (e.g. .ts → video/mp2t)
            if content_type and content_type.startswith(('image/', 'video/')):
                if _is_text_file(file_path):
                    content_type = 'text/plain'

            if content_type:
                if (not content_type.startswith(('image/', 'video/'))) or (
                    request.app.state.config.CONTENT_EXTRACTION_ENGINE == 'external'
                ):
                    await process_file(
                        request,
                        ProcessFileForm(file_id=file_item.id),
                        user=user,
                        db=db_session,
                    )
                else:
                    raise Exception(f'File type {content_type} is not supported for processing')
            else:
                log.info(f'File type {file.content_type} is not provided, but trying to process anyway')
                await process_file(
                    request,
                    ProcessFileForm(file_id=file_item.id),
                    user=user,
                    db=db_session,
                )

        except Exception as e:
            log.error(f'Error processing file: {file_item.id}')
            await Files.update_file_data_by_id(
                file_item.id,
                {
                    'status': 'failed',
                    'error': str(e.detail) if hasattr(e, 'detail') else str(e),
                },
                db=db_session,
            )

    try:
        if db:
            await _process_handler(db)
        else:
            async with get_async_db_context() as db_session:
                await _process_handler(db_session)
    finally:
        _cleanup_local_cache(file_path)


@router.post('/', response_model=FileModelResponse)
async def upload_file(
    request: Request,
    background_tasks: BackgroundTasks,
    file: UploadFile = File(...),
    metadata: Optional[dict | str] = Form(None),
    process: bool = Query(True),
    process_in_background: bool = Query(True),
    user=Depends(get_verified_user),
    db: AsyncSession = Depends(get_async_session),
):
    return await upload_file_handler(
        request,
        file=file,
        metadata=metadata,
        process=process,
        process_in_background=process_in_background,
        user=user,
        background_tasks=background_tasks,
        db=db,
    )


async def upload_file_handler(
    request: Request,
    file: UploadFile = File(...),
    metadata: Optional[dict | str] = Form(None),
    process: bool = Query(True),
    process_in_background: bool = Query(True),
    user=Depends(get_verified_user),
    background_tasks: Optional[BackgroundTasks] = None,
    db: Optional[AsyncSession] = None,
):
    log.info(f'file.content_type: {file.content_type} {process}')

    if isinstance(metadata, str):
        try:
            metadata = json.loads(metadata)
        except json.JSONDecodeError:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=ERROR_MESSAGES.DEFAULT('Invalid metadata format'),
            )
    file_metadata = metadata if metadata else {}

    try:
        unsanitized_filename = file.filename
        filename = os.path.basename(unsanitized_filename)

        file_extension = os.path.splitext(filename)[1]
        # Remove the leading dot from the file extension and lowercase it
        file_extension = file_extension[1:].lower() if file_extension else ''

        if process and request.app.state.config.ALLOWED_FILE_EXTENSIONS:
            request.app.state.config.ALLOWED_FILE_EXTENSIONS = [
                ext for ext in request.app.state.config.ALLOWED_FILE_EXTENSIONS if ext
            ]

            if file_extension not in request.app.state.config.ALLOWED_FILE_EXTENSIONS:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=ERROR_MESSAGES.DEFAULT(f'File type {file_extension} is not allowed'),
                )

        # replace filename with uuid
        id = str(uuid.uuid4())
        name = filename
        filename = f'{id}_{filename}'
        contents, file_path = await asyncio.to_thread(
            Storage.upload_file,
            file.file,
            filename,
            {
                'OpenWebUI-User-Email': user.email,
                'OpenWebUI-User-Id': user.id,
                'OpenWebUI-User-Name': user.name,
                'OpenWebUI-File-Id': id,
            },
        )

        file_item = await Files.insert_new_file(
            user.id,
            FileForm(
                **{
                    'id': id,
                    'filename': name,
                    'path': file_path,
                    'data': {
                        **({'status': 'pending'} if process else {}),
                    },
                    'meta': {
                        'name': name,
                        'content_type': (file.content_type if isinstance(file.content_type, str) else None),
                        'size': len(contents),
                        'data': file_metadata,
                    },
                }
            ),
            db=db,
        )

        if 'channel_id' in file_metadata:
            channel = await Channels.get_channel_by_id_and_user_id(file_metadata['channel_id'], user.id, db=db)
            if channel:
                await Channels.add_file_to_channel_by_id(channel.id, file_item.id, user.id, db=db)

        if process:
            if background_tasks and process_in_background:
                background_tasks.add_task(
                    process_uploaded_file,
                    request,
                    file,
                    file_path,
                    file_item,
                    file_metadata,
                    user,
                )
                return {'status': True, **file_item.model_dump()}
            else:
                await process_uploaded_file(
                    request,
                    file,
                    file_path,
                    file_item,
                    file_metadata,
                    user,
                    db=db,
                )
                return {'status': True, **file_item.model_dump()}
        else:
            if file_item:
                return file_item
            else:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=ERROR_MESSAGES.DEFAULT('Error uploading file'),
                )

    except HTTPException as e:
        raise e
    except Exception as e:
        log.exception(e)
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=ERROR_MESSAGES.DEFAULT('Error uploading file'),
        )


############################
# List Files
############################


PAGE_SIZE = 50


@router.get('/', response_model=FileListResponse)
async def list_files(
    user=Depends(get_verified_user),
    page: int = Query(1, ge=1, description='Page number (1-indexed)'),
    content: bool = Query(True),
    db: AsyncSession = Depends(get_async_session),
):
    skip = (page - 1) * PAGE_SIZE
    user_id = None if (user.role == 'admin' and BYPASS_ADMIN_ACCESS_CONTROL) else user.id

    result = await Files.get_file_list(user_id=user_id, skip=skip, limit=PAGE_SIZE, db=db)

    if not content:
        for file in result.items:
            if file.data and 'content' in file.data:
                del file.data['content']

    return result


############################
# Search Files
############################


@router.get('/search', response_model=list[FileModelResponse])
async def search_files(
    filename: str = Query(
        ...,
        description="Filename pattern to search for. Supports wildcards such as '*.txt'",
    ),
    content: bool = Query(True),
    skip: int = Query(0, ge=0, description='Number of files to skip'),
    limit: int = Query(100, ge=1, le=1000, description='Maximum number of files to return'),
    user=Depends(get_verified_user),
    db: AsyncSession = Depends(get_async_session),
):
    """
    Search for files by filename with support for wildcard patterns.
    Uses SQL-based filtering with pagination for better performance.
    """
    # Determine user_id: null for admin with bypass (search all), user.id otherwise
    user_id = None if (user.role == 'admin' and BYPASS_ADMIN_ACCESS_CONTROL) else user.id

    # Use optimized database query with pagination
    files = await Files.search_files(
        user_id=user_id,
        filename=filename,
        skip=skip,
        limit=limit,
        db=db,
    )

    if not files:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail='No files found matching the pattern.',
        )

    if not content:
        for file in files:
            if file.data and 'content' in file.data:
                del file.data['content']

    return files


############################
# Delete All Files
############################


@router.delete('/all')
async def delete_all_files(user=Depends(get_admin_user), db: AsyncSession = Depends(get_async_session)):
    result = await Files.delete_all_files(db=db)
    if result:
        try:
            await asyncio.to_thread(Storage.delete_all_files)
            await ASYNC_VECTOR_DB_CLIENT.reset()
        except Exception as e:
            log.exception(e)
            log.error('Error deleting files')
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=ERROR_MESSAGES.DEFAULT('Error deleting files'),
            )
        return {'message': 'All files deleted successfully'}
    else:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=ERROR_MESSAGES.DEFAULT('Error deleting files'),
        )


############################
# Get File By Id
############################


@router.get('/{id}', response_model=Optional[FileModel])
async def get_file_by_id(id: str, user=Depends(get_verified_user), db: AsyncSession = Depends(get_async_session)):
    file = await Files.get_file_by_id(id, db=db)

    if not file:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=ERROR_MESSAGES.NOT_FOUND,
        )

    return file


############################
# Get File Content By Id
############################


@router.get('/{id}/content')
async def get_file_content_by_id(id: str, user=Depends(get_verified_user), db: AsyncSession = Depends(get_async_session)):
    file = await Files.get_file_by_id(id, db=db)

    if not file:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=ERROR_MESSAGES.NOT_FOUND,
        )

    if not has_access_to_file(user, file):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=ERROR_MESSAGES.ACCESS_PROHIBITED,
        )

    if file.data and 'content' in file.data:
        return {'content': file.data['content']}
    else:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=ERROR_MESSAGES.NOT_FOUND,
        )


@router.get('/{id}/content/{file_path:path}')
async def get_file_content_by_id_and_path(
    id: str, file_path: str, user=Depends(get_verified_user), db: AsyncSession = Depends(get_async_session)
):
    file = await Files.get_file_by_id(id, db=db)

    if not file:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=ERROR_MESSAGES.NOT_FOUND,
        )

    if not has_access_to_file(user, file):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=ERROR_MESSAGES.ACCESS_PROHIBITED,
        )

    return {'content': 'Content not found'}


############################
# Download File By Id
############################


@router.get('/{id}/download')
async def download_file_by_id(id: str, user=Depends(get_verified_user), db: AsyncSession = Depends(get_async_session)):
    file = await Files.get_file_by_id(id, db=db)

    if not file:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=ERROR_MESSAGES.NOT_FOUND,
        )

    if not has_access_to_file(user, file):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=ERROR_MESSAGES.ACCESS_PROHIBITED,
        )

    file_path = await asyncio.to_thread(Storage.get_file, file.path)

    if os.path.isfile(file_path):
        return FileResponse(
            path=file_path,
            filename=file.filename,
            media_type='application/octet-stream',
        )
    else:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=ERROR_MESSAGES.NOT_FOUND,
        )
