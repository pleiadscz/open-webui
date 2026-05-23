<script lang="ts">
	import DOMPurify from 'dompurify';
	import { toast } from 'svelte-sonner';

	import { marked } from 'marked';
	import { v4 as uuidv4 } from 'uuid';
	import dayjs from '$lib/dayjs';
	import duration from 'dayjs/plugin/duration';
	import relativeTime from 'dayjs/plugin/relativeTime';

	dayjs.extend(duration);
	dayjs.extend(relativeTime);

	import { onMount, tick, getContext, createEventDispatcher } from 'svelte';

	import { createPicker, getAuthToken } from '$lib/utils/google-drive-picker';
	import { pickAndDownloadFile } from '$lib/utils/onedrive-file-picker';


	const dispatch = createEventDispatcher();

	import {
		type Model,
		mobile,
		settings,
		models,
		config,

		tools,
		toolServers,
		terminalServers,
		user as _user,
		showControls,
		showSettings,
		showCallOverlay,
		selectedTerminalId,

		temporaryChatEnabled
	} from '$lib/stores';

	import {
		convertHeicToJpeg,
		compressImage,
		createMessagesList,
		extractContentFromFile,
		extractCurlyBraceWords,
		extractInputVariables,
		getAge,
		getCurrentDateTime,
		getFormattedDate,
		getFormattedTime,
		getUserPosition,
		getUserTimezone,
		getWeekday
	} from '$lib/utils';
	import { uploadFile } from '$lib/apis/files';
	import { generateAutoCompletion } from '$lib/apis';
	import { deleteFileById } from '$lib/apis/files';
	import { getChatById } from '$lib/apis/chats';
	import { getSessionUser } from '$lib/apis/auths';
	import { getTools } from '$lib/apis/tools';

	import { WEBUI_BASE_URL, WEBUI_API_BASE_URL, PASTED_TEXT_CHARACTER_LIMIT } from '$lib/constants';
	import { getOAuthClientAuthorizationUrl } from '$lib/apis/configs';

	import { createNoteHandler } from '../notes/utils';
	import { getSuggestionRenderer } from '../common/RichTextInput/suggestions';

	import InputMenu from './MessageInput/InputMenu.svelte';


	import ToolServersModal from './ToolServersModal.svelte';

	import RichTextInput from '../common/RichTextInput.svelte';
	import Tooltip from '../common/Tooltip.svelte';
	import FileItem from '../common/FileItem.svelte';
	import Image from '../common/Image.svelte';
	import Spinner from '../common/Spinner.svelte';

	import XMark from '../icons/XMark.svelte';
	import GlobeAlt from '../icons/GlobeAlt.svelte';
	import Photo from '../icons/Photo.svelte';
	import Wrench from '../icons/Wrench.svelte';
	import Sparkles from '../icons/Sparkles.svelte';

	import InputVariablesModal from './MessageInput/InputVariablesModal.svelte';

	import Terminal from '../icons/Terminal.svelte';
	import IntegrationsMenu from './MessageInput/IntegrationsMenu.svelte';
	import TerminalMenu from './MessageInput/TerminalMenu.svelte';
	import Component from '../icons/Component.svelte';
		import PlusAlt from '../icons/PlusAlt.svelte';
import { Plus, ArrowUp, Square, Globe } from 'lucide-svelte';
		import Dropdown from '../common/Dropdown.svelte';

		import CommandSuggestionList from './MessageInput/CommandSuggestionList.svelte';
	import Knobs from '../icons/Knobs.svelte';
	import ValvesModal from '../workspace/common/ValvesModal.svelte';
	import Note from '../icons/Note.svelte';
	import { goto } from '$app/navigation';
	import InputModal from '../common/InputModal.svelte';
	import Expand from '../icons/Expand.svelte';
	import QueuedMessageItem from './MessageInput/QueuedMessageItem.svelte';
	import TaskList from './Messages/ResponseMessage/TaskList.svelte';

	const i18n = getContext('i18n');

	export let onUpload: Function = (e) => {};
	export let onChange: Function = () => {};

	export let createMessagePair: Function;
	export let stopResponse: Function;

	export let autoScroll = false;
	export let generating = false;
	export let uploadPending = false;

	export let atSelectedModel: Model | undefined = undefined;
	export let selectedModels: [''];

	let selectedModelIds = [];
	$: selectedModelIds = atSelectedModel !== undefined ? [atSelectedModel.id] : selectedModels;

	export let history;
	export let taskIds = null;

	$: isActive =
		(taskIds && taskIds.length > 0) ||
		(history.currentId && history.messages[history.currentId]?.done != true) ||
		generating;

	export let prompt = '';
	export let files = [];

	export let selectedToolIds = [];
	export let selectedFilterIds = [];

	export let imageGenerationEnabled = false;
	export let webSearchEnabled = false;
	export let codeInterpreterEnabled = false;


	export let pendingOAuthTools = [];

	let showTerminalMenu = false;

	export let messageQueue: { id: string; prompt: string; files: any[] }[] = [];
	export let onQueueSendNow: (id: string) => void = () => {};
	export let onQueueEdit: (id: string) => void = () => {};
	export let onQueueDelete: (id: string) => void = () => {};

	export let chatTasks = [];

	let inputContent = null;

	let showInputVariablesModal = false;
	let inputVariablesModalCallback = (variableValues) => {};
	let inputVariables = {};
	let inputVariableValues = {};

	let showValvesModal = false;
	let selectedValvesType = 'tool'; // 'tool' or 'function'
	let selectedValvesItemId = null;
	let integrationsMenuCloseOnOutsideClick = true;

	$: if (!showValvesModal) {
		integrationsMenuCloseOnOutsideClick = true;
	}

	$: onChange({
		prompt,
		files: files
			.filter((file) => file.type !== 'image')
			.map((file) => {
				return {
					...file,
					user: undefined,
					access_grants: undefined
				};
			}),
		selectedToolIds,
		selectedFilterIds,
		imageGenerationEnabled,
		webSearchEnabled,
		codeInterpreterEnabled
	});

	const inputVariableHandler = async (text: string): Promise<string> => {
		inputVariables = extractInputVariables(text);

		// No variables? return the original text immediately.
		if (Object.keys(inputVariables).length === 0) {
			return text;
		}

		// Show modal and wait for the user's input.
		showInputVariablesModal = true;
		return await new Promise<string>((resolve) => {
			inputVariablesModalCallback = (variableValues) => {
				inputVariableValues = { ...inputVariableValues, ...variableValues };
				replaceVariables(inputVariableValues);
				showInputVariablesModal = false;
				resolve(text);
			};
		});
	};

	const textVariableHandler = async (text: string) => {
		if (text.includes('{{CLIPBOARD}}')) {
			const clipboardText = await navigator.clipboard.readText().catch((err) => {
				toast.error($i18n.t('Failed to read clipboard contents'));
				return '{{CLIPBOARD}}';
			});

			const clipboardItems = await navigator.clipboard.read().catch((err) => {
				console.error('Failed to read clipboard items:', err);
				return [];
			});

			for (const item of clipboardItems) {
				for (const type of item.types) {
					if (type.startsWith('image/')) {
						const blob = await item.getType(type);
						const file = new File([blob], `clipboard-image.${type.split('/')[1]}`, {
							type: type
						});

						inputFilesHandler([file]);
					}
				}
			}

			text = text.replaceAll('{{CLIPBOARD}}', clipboardText.replaceAll('\r\n', '\n'));
		}

		if (text.includes('{{USER_LOCATION}}')) {
			let location;
			try {
				location = await getUserPosition();
			} catch (error) {
				toast.error($i18n.t('Location access not allowed'));
				location = 'LOCATION_UNKNOWN';
			}
			text = text.replaceAll('{{USER_LOCATION}}', String(location));
		}

		const sessionUser = await getSessionUser(localStorage.token);

		if (text.includes('{{USER_NAME}}')) {
			const name = sessionUser?.name || 'User';
			text = text.replaceAll('{{USER_NAME}}', name);
		}

		if (text.includes('{{USER_EMAIL}}')) {
			const email = sessionUser?.email || '';

			if (email) {
				text = text.replaceAll('{{USER_EMAIL}}', email);
			}
		}

		if (text.includes('{{USER_BIO}}')) {
			const bio = sessionUser?.bio || '';

			if (bio) {
				text = text.replaceAll('{{USER_BIO}}', bio);
			}
		}

		if (text.includes('{{USER_GENDER}}')) {
			const gender = sessionUser?.gender || '';

			if (gender) {
				text = text.replaceAll('{{USER_GENDER}}', gender);
			}
		}

		if (text.includes('{{USER_BIRTH_DATE}}')) {
			const birthDate = sessionUser?.date_of_birth || '';

			if (birthDate) {
				text = text.replaceAll('{{USER_BIRTH_DATE}}', birthDate);
			}
		}

		if (text.includes('{{USER_AGE}}')) {
			const birthDate = sessionUser?.date_of_birth || '';

			if (birthDate) {
				// calculate age using date
				const age = getAge(birthDate);
				text = text.replaceAll('{{USER_AGE}}', age);
			}
		}

		if (text.includes('{{USER_LANGUAGE}}')) {
			const language = localStorage.getItem('locale') || 'en-US';
			text = text.replaceAll('{{USER_LANGUAGE}}', language);
		}

		if (text.includes('{{CURRENT_DATE}}')) {
			const date = getFormattedDate();
			text = text.replaceAll('{{CURRENT_DATE}}', date);
		}

		if (text.includes('{{CURRENT_TIME}}')) {
			const time = getFormattedTime();
			text = text.replaceAll('{{CURRENT_TIME}}', time);
		}

		if (text.includes('{{CURRENT_DATETIME}}')) {
			const dateTime = getCurrentDateTime();
			text = text.replaceAll('{{CURRENT_DATETIME}}', dateTime);
		}

		if (text.includes('{{CURRENT_TIMEZONE}}')) {
			const timezone = getUserTimezone();
			text = text.replaceAll('{{CURRENT_TIMEZONE}}', timezone);
		}

		if (text.includes('{{CURRENT_WEEKDAY}}')) {
			const weekday = getWeekday();
			text = text.replaceAll('{{CURRENT_WEEKDAY}}', weekday);
		}

		return text;
	};

	const replaceVariables = (variables: Record<string, any>) => {
		console.log('Replacing variables:', variables);

		const chatInput = document.getElementById('chat-input');

		if (chatInput) {
			chatInputElement.replaceVariables(variables);
			chatInputElement.focus();
		}
	};

	export const setText = async (text?: string, cb?: (text: string) => void) => {
		const chatInput = document.getElementById('chat-input');

		if (chatInput) {
			if (text !== '') {
				text = await textVariableHandler(text || '');
			}

			chatInputElement?.setText(text);
			if (!$showCallOverlay) {
				chatInputElement?.focus();
			}

			if (text !== '') {
				text = await inputVariableHandler(text);
			}

			await tick();
			if (cb) await cb(text);
		}
	};

	const getCommand = () => {
		const chatInput = document.getElementById('chat-input');
		let word = '';

		if (chatInput) {
			word = chatInputElement?.getWordAtDocPos();
		}

		return word;
	};

	const replaceCommandWithText = (text) => {
		const chatInput = document.getElementById('chat-input');
		if (!chatInput) return;

		chatInputElement?.replaceCommandWithText(text);
	};

	const insertTextAtCursor = async (text: string) => {
		const chatInput = document.getElementById('chat-input');
		if (!chatInput) return;

		text = await textVariableHandler(text);

		if (command) {
			replaceCommandWithText(text);
		} else {
			chatInputElement?.insertContent(text);
		}

		await tick();
		text = await inputVariableHandler(text);
		await tick();

		const chatInputContainer = document.getElementById('chat-input-container');
		if (chatInputContainer) {
			chatInputContainer.scrollTop = chatInputContainer.scrollHeight;
		}

		await tick();
		if (chatInput) {
			chatInput.focus();
			chatInput.dispatchEvent(new Event('input'));

			const words = extractCurlyBraceWords(prompt);

			if (words.length > 0) {
				const word = words.at(0);
				await tick();
			} else {
				chatInput.scrollTop = chatInput.scrollHeight;
			}
		}
	};

	let command = '';
	export let showCommands = false;
	$: showCommands =
		['/', '#', '@', '$', ':'].includes(command?.charAt(0)) || '\\#' === command?.slice(0, 2);
		let suggestions = null;

		let showTools = false;

    const CAMERA_ICON = `<svg width="24" height="24" viewBox="0 0 24 24" fill="currentColor">
    <path d="M12 4C10.8908 4 9.92091 4.60141 9.40069 5.50073C9.22194 5.80972 8.89205 6 8.53508 6H7.8C6.94342 6 6.36113 6.00078 5.91104 6.03755C5.47262 6.07337 5.24842 6.1383 5.09202 6.21799C4.7157 6.40973 4.40973 6.71569 4.21799 7.09202C4.1383 7.24842 4.07337 7.47262 4.03755 7.91104C4.00078 8.36113 4 8.94342 4 9.8V15.2C4 16.0566 4.00078 16.6389 4.03755 17.089C4.07337 17.5274 4.1383 17.7516 4.21799 17.908C4.40973 18.2843 4.7157 18.5903 5.09202 18.782C5.24842 18.8617 5.47262 18.9266 5.91104 18.9624C6.36113 18.9992 6.94342 19 7.8 19H16.2C17.0566 19 17.6389 18.9992 18.089 18.9624C18.5274 18.9266 18.7516 18.8617 18.908 18.782C19.2843 18.5903 19.5903 18.2843 19.782 17.908C19.8617 17.7516 19.9266 17.5274 19.9624 17.089C19.9992 16.6389 20 16.0566 20 15.2V9.8C20 8.94342 19.9992 8.36113 19.9624 7.91104C19.9266 7.47262 19.8617 7.24842 19.782 7.09202C19.5903 6.71569 19.2843 6.40973 18.908 6.21799C18.7516 6.1383 18.5274 6.07337 18.089 6.03755C17.6389 6.00078 17.0566 6 16.2 6H15.4648C15.1079 6 14.778 5.80972 14.5992 5.50073C14.079 4.60141 13.1091 4 12 4ZM7.99973 4C8.91084 2.78702 10.363 2 12 2C13.6369 2 15.0891 2.78702 16.0002 4L16.2413 4C17.0463 3.99999 17.7106 3.99998 18.2518 4.04419C18.8139 4.09012 19.3306 4.18868 19.816 4.43597C20.5686 4.81947 21.1805 5.43139 21.564 6.18404C21.8113 6.66937 21.9099 7.18608 21.9558 7.74817C22 8.28936 22 8.95372 22 9.75868V15.2413C22 16.0463 22 16.7106 21.9558 17.2518C21.9099 17.8139 21.8113 18.3306 21.564 18.816C21.1805 19.5686 20.5686 20.1805 19.816 20.564C19.3306 20.8113 18.8139 20.9099 18.2518 20.9558C17.7106 21 17.0463 21 16.2413 21H7.75868C6.95372 21 6.28936 21 5.74817 20.9558C5.18608 20.9099 4.66937 20.8113 4.18404 20.564C3.43139 20.1805 2.81947 19.5686 2.43597 18.816C2.18868 18.3306 2.09012 17.8139 2.04419 17.2518C1.99998 16.7106 1.99999 16.0463 2 15.2413V9.7587C1.99999 8.95373 1.99998 8.28937 2.04419 7.74817C2.09012 7.18608 2.18868 6.66937 2.43597 6.18404C2.81947 5.43139 3.43139 4.81947 4.18404 4.43597C4.66937 4.18868 5.18608 4.09012 5.74817 4.04419C6.28937 3.99998 6.95373 3.99999 7.7587 4L7.99973 4ZM12 10C10.7573 10 9.74995 11.0074 9.74995 12.25C9.74995 13.4926 10.7573 14.5 12 14.5C13.2426 14.5 14.25 13.4926 14.25 12.25C14.25 11.0074 13.2426 10 12 10ZM7.74995 12.25C7.74995 9.90279 9.65274 8 12 8C14.3472 8 16.25 9.90279 16.25 12.25C16.25 14.5972 14.3472 16.5 12 16.5C9.65274 16.5 7.74995 14.5972 7.74995 12.25Z" />
  </svg>`

    const PHOTO_ICON = `<svg width="24" height="24" viewBox="0 0 24 24" fill="currentColor">
    <path d="M8.7587 3H15.2413C16.0463 2.99999 16.7106 2.99998 17.2518 3.04419C17.8139 3.09012 18.3306 3.18868 18.816 3.43597C19.5686 3.81947 20.1805 4.43139 20.564 5.18404C20.8113 5.66937 20.9099 6.18608 20.9558 6.74817C21 7.28936 21 7.95372 21 8.75868V15.2413C21 16.0463 21 16.7106 20.9558 17.2518C20.9099 17.8139 20.8113 18.3306 20.564 18.816C20.1805 19.5686 19.5686 20.1805 18.816 20.564C18.3306 20.8113 17.8139 20.9099 17.2518 20.9558C16.7106 21 16.0463 21 15.2413 21H8.75868C7.95372 21 7.28936 21 6.74817 20.9558C6.18608 20.9099 5.66937 20.8113 5.18404 20.564C4.43139 20.1805 3.81947 19.5686 3.43597 18.816C3.18868 18.3306 3.09012 17.8139 3.04419 17.2518C2.99998 16.7106 2.99999 16.0463 3 15.2413V8.7587C2.99999 7.95373 2.99998 7.28937 3.04419 6.74817C3.09012 6.18608 3.18868 5.66937 3.43597 5.18404C3.81947 4.43139 4.43139 3.81947 5.18404 3.43597C5.66937 3.18868 6.18608 3.09012 6.74817 3.04419C7.28937 2.99998 7.95373 2.99999 8.7587 3ZM6.91104 5.03755C6.47262 5.07337 6.24842 5.1383 6.09202 5.21799C5.7157 5.40973 5.40973 5.7157 5.21799 6.09202C5.1383 6.24842 5.07337 6.47262 5.03755 6.91104C5.00078 7.36113 5 7.94342 5 8.8V13.5857L5.87868 12.707C7.05026 11.5355 8.94975 11.5355 10.1213 12.7071L16.4073 18.9931C16.6681 18.9878 16.8913 18.9786 17.089 18.9624C17.5274 18.9266 17.7516 18.8617 17.908 18.782C18.2843 18.5903 18.5903 18.2843 18.782 17.908C18.8617 17.7516 18.9266 17.5274 18.9624 17.089C18.9992 16.6389 19 16.0566 19 15.2V8.8C19 7.94342 18.9992 7.36113 18.9624 6.91104C18.9266 6.47262 18.8617 6.24842 18.782 6.09202C18.5903 5.7157 18.2843 5.40973 17.908 5.21799C17.7516 5.1383 17.5274 5.07337 17.089 5.03755C16.6389 5.00078 16.0566 5 15.2 5H8.8C7.94342 5 7.36113 5.00078 6.91104 5.03755ZM13.5858 19L8.70711 14.1213C8.31658 13.7307 7.68342 13.7307 7.2929 14.1213L5.00694 16.4072C5.01219 16.668 5.0214 16.8912 5.03755 17.089C5.07337 17.5274 5.1383 17.7516 5.21799 17.908C5.40973 18.2843 5.7157 18.5903 6.09202 18.782C6.24842 18.8617 6.47262 18.9266 6.91104 18.9624C7.36113 18.9992 7.94342 19 8.8 19H13.5858ZM14.5 8.5C13.9477 8.5 13.5 8.94772 13.5 9.5C13.5 10.0523 13.9477 10.5 14.5 10.5C15.0523 10.5 15.5 10.0523 15.5 9.5C15.5 8.94772 15.0523 8.5 14.5 8.5ZM11.5 9.5C11.5 7.84315 12.8431 6.5 14.5 6.5C16.1569 6.5 17.5 7.84315 17.5 9.5C17.5 11.1569 16.1569 12.5 14.5 12.5C12.8431 12.5 11.5 11.1569 11.5 9.5Z" />
  </svg>`

    const FILE_ICON = `<svg width="24" height="24" viewBox="0 0 24 24" fill="currentColor">
    <path fillRule="evenodd" d="M9 7a5 5 0 0 1 10 0v8a7 7 0 1 1-14 0V9a1 1 0 0 1 2 0v6a5 5 0 0 0 10 0V7a3 3 0 1 0-6 0v8a1 1 0 1 0 2 0V9a1 1 0 1 1 2 0v6a3 3 0 1 1-6 0V7Z" clipRule="evenodd" />
  </svg>`

    const MENU_ITEMS = [
        { icon: CAMERA_ICON, label: 'Aparat' },
        { icon: PHOTO_ICON, label: 'Zdjęcia' },
        { icon: FILE_ICON, label: 'Pliki' }
    ];

    let openPlusMenu = false;
    let cameraInputRef: HTMLInputElement | null = null;
    let photosInputRef: HTMLInputElement | null = null;

    function handlePlusPick(kind: 'camera' | 'photos' | 'files') {
        openPlusMenu = false;
        if (kind === 'camera') {
            cameraInputRef?.click();
            return;
        }
        if (kind === 'photos') {
            photosInputRef?.click();
            return;
        }
        filesInputElement?.click();
    }

			let loaded = false;


	let isComposing = false;
	// Safari has a bug where compositionend is not triggered correctly #16615
	// when using the virtual keyboard on iOS.
	let compositionEndedAt = -2e8;
	const isSafari = /^((?!chrome|android).)*safari/i.test(navigator.userAgent);
	function inOrNearComposition(event: Event) {
		if (isComposing) {
			return true;
		}
		// See https://www.stum.de/2016/06/24/handling-ime-events-in-javascript/.
		// On Japanese input method editors (IMEs), the Enter key is used to confirm character
		// selection. On Safari, when Enter is pressed, compositionend and keydown events are
		// emitted. The keydown event triggers newline insertion, which we don't want.
		// This method returns true if the keydown event should be ignored.
		// We only ignore it once, as pressing Enter a second time *should* insert a newline.
		// Furthermore, the keydown event timestamp must be close to the compositionEndedAt timestamp.
		// This guards against the case where compositionend is triggered without the keyboard
		// (e.g. character confirmation may be done with the mouse), and keydown is triggered
		// afterwards- we wouldn't want to ignore the keydown event in this case.
		if (isSafari && Math.abs(event.timeStamp - compositionEndedAt) < 500) {
			compositionEndedAt = -2e8;
			return true;
		}
		return false;
	}

	let chatInputContainerElement;
	let chatInputElement;

	let filesInputElement;
	let commandsElement;

	let inputFiles;

	let showInputModal = false;

	export let dragged = false;
	let shiftKey = false;

	let user = null;
	export let placeholder = '';

	let visionCapableModels = [];
	$: visionCapableModels = (atSelectedModel?.id ? [atSelectedModel.id] : selectedModels).filter(
		(model) => $models.find((m) => m.id === model)?.info?.meta?.capabilities?.vision ?? true
	);

	let fileUploadCapableModels = [];
	$: fileUploadCapableModels = (atSelectedModel?.id ? [atSelectedModel.id] : selectedModels).filter(
		(model) => $models.find((m) => m.id === model)?.info?.meta?.capabilities?.file_upload ?? true
	);

	let webSearchCapableModels = [];
	$: webSearchCapableModels = (atSelectedModel?.id ? [atSelectedModel.id] : selectedModels).filter(
		(model) => $models.find((m) => m.id === model)?.info?.meta?.capabilities?.web_search ?? true
	);

	let imageGenerationCapableModels = [];
	$: imageGenerationCapableModels = (
		atSelectedModel?.id ? [atSelectedModel.id] : selectedModels
	).filter(
		(model) =>
			$models.find((m) => m.id === model)?.info?.meta?.capabilities?.image_generation ?? true
	);



	let terminalCapableModels = [];
	$: terminalCapableModels = (atSelectedModel?.id ? [atSelectedModel.id] : selectedModels).filter(
		(model) => $models.find((m) => m.id === model)?.info?.meta?.capabilities?.terminal ?? true
	);

	let toggleFilters = [];
	$: toggleFilters = (atSelectedModel?.id ? [atSelectedModel.id] : selectedModels)
		.map((id) => ($models.find((model) => model.id === id) || {})?.filters ?? [])
		.reduce((acc, filters) => acc.filter((f1) => filters.some((f2) => f2.id === f1.id)));

	let showToolsButton = false;
	$: showToolsButton = ($tools ?? []).length > 0 || ($toolServers ?? []).length > 0;

	let showWebSearchButton = false;
	$: showWebSearchButton =
		(atSelectedModel?.id ? [atSelectedModel.id] : selectedModels).length ===
			webSearchCapableModels.length &&
		$config?.features?.enable_web_search &&
		($_user.role === 'admin' || $_user?.permissions?.features?.web_search);

	let showImageGenerationButton = false;
	$: showImageGenerationButton =
		(atSelectedModel?.id ? [atSelectedModel.id] : selectedModels).length ===
			imageGenerationCapableModels.length &&
		$config?.features?.enable_image_generation &&
		($_user.role === 'admin' || $_user?.permissions?.features?.image_generation);

	let showCodeInterpreterButton = false;
	$: showCodeInterpreterButton =
		!$selectedTerminalId &&
		(atSelectedModel?.id ? [atSelectedModel.id] : selectedModels).length ===
			codeInterpreterCapableModels.length &&
		$config?.features?.enable_code_interpreter &&
		($_user.role === 'admin' || $_user?.permissions?.features?.code_interpreter);

	// Disable code interpreter when terminal is active (mutually exclusive)
	$: if ($selectedTerminalId && codeInterpreterEnabled) {
		codeInterpreterEnabled = false;
	}

	// Clear selected terminal when model doesn't support terminal
	$: if ($selectedTerminalId && terminalCapableModels.length === 0) {
		selectedTerminalId.set(null);
	}

	const scrollToBottom = () => {
		const element = document.getElementById('messages-container');
		element.scrollTo({
			top: element.scrollHeight,
			behavior: 'smooth'
		});
	};

	const screenCaptureHandler = async () => {
		try {
			// Request screen media
			const mediaStream = await navigator.mediaDevices.getDisplayMedia({
				video: { cursor: 'never' },
				audio: false
			});
			// Once the user selects a screen, temporarily create a video element
			const video = document.createElement('video');
			video.srcObject = mediaStream;
			// Ensure the video loads without affecting user experience or tab switching
			await video.play();
			// Set up the canvas to match the video dimensions
			const canvas = document.createElement('canvas');
			canvas.width = video.videoWidth;
			canvas.height = video.videoHeight;
			// Grab a single frame from the video stream using the canvas
			const context = canvas.getContext('2d');
			context.drawImage(video, 0, 0, canvas.width, canvas.height);
			// Stop all video tracks (stop screen sharing) after capturing the image
			mediaStream.getTracks().forEach((track) => track.stop());

			// bring back focus to this current tab, so that the user can see the screen capture
			window.focus();

			// Convert the canvas to a Base64 image URL
			const imageUrl = canvas.toDataURL('image/png');
			const blob = await (await fetch(imageUrl)).blob();
			const file = new File([blob], `screen-capture-${Date.now()}.png`, { type: 'image/png' });
			inputFilesHandler([file]);
			// Clean memory: Clear video srcObject
			video.srcObject = null;
		} catch (error) {
			// Handle any errors (e.g., user cancels screen sharing)
			console.error('Error capturing screen:', error);
		}
	};

	const uploadFileHandler = async (file, process = true, itemData = {}) => {
		if ($_user?.role !== 'admin' && !($_user?.permissions?.chat?.file_upload ?? true)) {
			toast.error($i18n.t('You do not have permission to upload files.'));
			return null;
		}

		if (fileUploadCapableModels.length !== selectedModels.length) {
			toast.error($i18n.t('Model(s) do not support file upload'));
			return null;
		}

		const tempItemId = uuidv4();
		const fileItem = {
			type: 'file',
			file: '',
			id: null,
			url: '',
			name: file.name,
			collection_name: '',
			status: 'uploading',
			size: file.size,
			error: '',
			itemId: tempItemId,
			...itemData
		};

		if (fileItem.size == 0) {
			toast.error($i18n.t('You cannot upload an empty file.'));
			return null;
		}

		files = [...files, fileItem];

		if (!$temporaryChatEnabled) {
			try {
				// If the file is an audio file, provide the language for STT.
				let metadata = null;
				if (
					(file.type.startsWith('audio/') || file.type.startsWith('video/')) &&
					$settings?.audio?.stt?.language
				) {
					metadata = {
						language: $settings?.audio?.stt?.language
					};
				}

				// During the file upload, file content is automatically extracted.
				const uploadedFile = await uploadFile(localStorage.token, file, metadata, process);

				if (uploadedFile) {
					console.log('File upload completed:', {
						id: uploadedFile.id,
						name: fileItem.name,
						collection: uploadedFile?.meta?.collection_name
					});

					if (uploadedFile.error) {
						console.warn('File upload warning:', uploadedFile.error);
						toast.warning(uploadedFile.error);
					}

					fileItem.status = 'uploaded';
					fileItem.file = uploadedFile;
					fileItem.id = uploadedFile.id;
					fileItem.collection_name =
						uploadedFile?.meta?.collection_name || uploadedFile?.collection_name;
					fileItem.content_type = uploadedFile.meta?.content_type || uploadedFile.content_type;
					fileItem.url = `${uploadedFile.id}`;

					files = files;
				} else {
					files = files.filter((item) => item?.itemId !== tempItemId);
				}
			} catch (e) {
				toast.error(`${e}`);
				files = files.filter((item) => item?.itemId !== tempItemId);
			}
		} else {
			// If temporary chat is enabled, we just add the file to the list without uploading it.

			const content = await extractContentFromFile(file).catch((error) => {
				toast.error(
					$i18n.t('Failed to extract content from the file: {{error}}', { error: error })
				);
				return null;
			});

			if (content === null) {
				toast.error($i18n.t('Failed to extract content from the file.'));
				files = files.filter((item) => item?.itemId !== tempItemId);
				return null;
			} else {
				console.log('Extracted content from file:', {
					name: file.name,
					size: file.size,
					content: content
				});

				fileItem.status = 'uploaded';
				fileItem.type = 'text';
				fileItem.content = content;
				fileItem.id = uuidv4(); // Temporary ID for the file

				files = files;
			}
		}
	};

	const inputFilesHandler = async (inputFiles) => {
		console.log('Input files handler called with:', inputFiles);

		if (
			($config?.file?.max_count ?? null) !== null &&
			files.length + inputFiles.length > $config?.file?.max_count
		) {
			toast.error(
				$i18n.t(`You can only chat with a maximum of {{maxCount}} file(s) at a time.`, {
					maxCount: $config?.file?.max_count
				})
			);
			return;
		}

		inputFiles.forEach(async (file) => {
			console.log('Processing file:', {
				name: file.name,
				type: file.type,
				size: file.size,
				extension: file.name.split('.').at(-1)
			});

			if (
				($config?.file?.max_size ?? null) !== null &&
				file.size > ($config?.file?.max_size ?? 0) * 1024 * 1024
			) {
				console.log('File exceeds max size limit:', {
					fileSize: file.size,
					maxSize: ($config?.file?.max_size ?? 0) * 1024 * 1024
				});
				toast.error(
					$i18n.t(`File size should not exceed {{maxSize}} MB.`, {
						maxSize: $config?.file?.max_size
					})
				);
				return;
			}

			if (file['type'].startsWith('image/')) {
				if (visionCapableModels.length === 0) {
					toast.error($i18n.t('Selected model(s) do not support image inputs'));
					return;
				}

				const compressImageHandler = async (imageUrl, settings = {}, config = {}) => {
					// Quick shortcut so we don’t do unnecessary work.
					const settingsCompression = settings?.imageCompression ?? false;
					const configWidth = config?.file?.image_compression?.width ?? null;
					const configHeight = config?.file?.image_compression?.height ?? null;

					// If neither settings nor config wants compression, return original URL.
					if (!settingsCompression && !configWidth && !configHeight) {
						return imageUrl;
					}

					// Default to null (no compression unless set)
					let width = null;
					let height = null;

					// If user/settings want compression, pick their preferred size.
					if (settingsCompression) {
						width = settings?.imageCompressionSize?.width ?? null;
						height = settings?.imageCompressionSize?.height ?? null;
					}

					// Apply config limits as an upper bound if any
					if (configWidth && (width === null || width > configWidth)) {
						width = configWidth;
					}
					if (configHeight && (height === null || height > configHeight)) {
						height = configHeight;
					}

					// Do the compression if required
					if (width || height) {
						return await compressImage(imageUrl, width, height);
					}
					return imageUrl;
				};

				let reader = new FileReader();

				reader.onload = async (event) => {
					let imageUrl = event.target.result;

					// Compress the image if settings or config require it
					imageUrl = await compressImageHandler(imageUrl, $settings, $config);

					if ($temporaryChatEnabled) {
						files = [
							...files,
							{
								type: 'image',
								url: imageUrl
							}
						];
					} else {
						const blob = await (await fetch(imageUrl)).blob();
						const compressedFile = new File([blob], file.name, { type: file.type });

						uploadFileHandler(compressedFile, false);
					}
				};

				reader.readAsDataURL(file['type'] === 'image/heic' ? await convertHeicToJpeg(file) : file);
			} else {
				uploadFileHandler(file);
			}
		});
	};

	const createNote = async () => {
		if (inputContent?.md.trim() === '' && inputContent?.html.trim() === '') {
			toast.error($i18n.t('Cannot create an empty note.'));
			return;
		}

		const res = await createNoteHandler(
			dayjs().format('YYYY-MM-DD'),
			inputContent?.md,
			inputContent?.html
		);

		if (res) {
			// Clear the input content saved in session storage.
			sessionStorage.removeItem('chat-input');
			goto(`/notes/${res.id}`);
		}
	};

	const onDragOver = (e: DragEvent) => {
		e.preventDefault();

		// Check if a file or a sidebar chat item is being dragged.
		if (e.dataTransfer?.types?.includes('Files') || e.dataTransfer?.types?.includes('text/plain')) {
			dragged = true;
		} else {
			dragged = false;
		}
	};

	const onDragLeave = (e: DragEvent) => {
		if ((e.currentTarget as HTMLElement)?.contains(e.relatedTarget as Node)) {
			return;
		}
		dragged = false;
	};

	const onDrop = async (e: DragEvent) => {
		e.preventDefault();
		console.log(e);

		// Check if the dropped data is a sidebar chat item
		const textData = e.dataTransfer?.getData('text/plain');
		if (textData) {
			try {
				const data = JSON.parse(textData);
				if (data.type === 'chat' && data.id) {
					// Fetch the chat to get its title, then add as a reference chat
					const chat = await getChatById(localStorage.token, data.id);
					if (chat) {
						const chatItem = {
							type: 'chat',
							id: chat.id,
							name: chat.title,
							collection_name: '',
							status: 'processed'
						};
						if (!files.find((f) => f.id === chatItem.id)) {
							files = [...files, chatItem];
						}
					}
					dragged = false;
					e.stopPropagation();
					return;
				}
			} catch (_) {
				// Not valid JSON — fall through to file handling
			}
		}

		if (e.dataTransfer?.files) {
			const inputFiles = Array.from(e.dataTransfer?.files);
			if (inputFiles && inputFiles.length > 0) {
				console.log(inputFiles);
				inputFilesHandler(inputFiles);
			}
		}

		dragged = false;
	};

	const onKeyDown = (e: KeyboardEvent) => {
		if (e.key === 'Shift') {
			shiftKey = true;
		}

		// Cmd/Ctrl+Shift+L to toggle dictation
		if (e.key.toLowerCase() === 'l' && (e.metaKey || e.ctrlKey) && e.shiftKey) {
			e.preventDefault();
			if (recording) {
				// Confirm and stop recording
				document.getElementById('confirm-recording-button')?.click();
			} else {
				// Start recording (same logic as voice-input-button click)
				document.getElementById('voice-input-button')?.click();
			}
			return;
		}

		if (e.key === 'Escape') {
			console.log('Escape');
			dragged = false;
		}
	};

	const onKeyUp = (e: KeyboardEvent) => {
		if (e.key === 'Shift') {
			shiftKey = false;
		}
	};

	const onFocus = () => {};

	const onBlur = () => {
		shiftKey = false;
	};

	onMount(() => {
		suggestions = [
			{
				char: '@',
				render: getSuggestionRenderer(CommandSuggestionList, {
					i18n,
					onSelect: (e) => {
						const { type, data } = e;

						if (type === 'model') {
							atSelectedModel = data;
						}

						document.getElementById('chat-input')?.focus();
					},

					insertTextHandler: insertTextAtCursor,
					onUpload: (e) => {
						const { type, data } = e;

						if (type === 'file') {
							if (files.find((f) => f.id === data.id)) {
								return;
							}
							files = [
								...files,
								{
									...data,
									status: 'processed'
								}
							];
						} else {
							if (files.find((f) => f.url === data || f.name === data)) {
								return;
							}
							onUpload(e);
						}
					}
				})
			},
			{
				char: '/',
				render: getSuggestionRenderer(CommandSuggestionList, {
					i18n,
					onSelect: (e) => {
						const { type, data } = e;

						if (type === 'model') {
							atSelectedModel = data;
						}

						document.getElementById('chat-input')?.focus();
					},

					insertTextHandler: insertTextAtCursor,
					onUpload: (e) => {
						const { type, data } = e;

						if (type === 'file') {
							if (files.find((f) => f.id === data.id)) {
								return;
							}
							files = [
								...files,
								{
									...data,
									status: 'processed'
								}
							];
						} else {
							if (files.find((f) => f.url === data || f.name === data)) {
								return;
							}
							onUpload(e);
						}
					}
				})
			},
			{
				char: '#',
				render: getSuggestionRenderer(CommandSuggestionList, {
					i18n,
					onSelect: (e) => {
						const { type, data } = e;

						if (type === 'model') {
							atSelectedModel = data;
						}

						document.getElementById('chat-input')?.focus();
					},

					insertTextHandler: insertTextAtCursor,
					onUpload: (e) => {
						const { type, data } = e;

						if (type === 'file') {
							if (files.find((f) => f.id === data.id)) {
								return;
							}
							files = [
								...files,
								{
									...data,
									status: 'processed'
								}
							];
						} else {
							if (files.find((f) => f.url === data || f.name === data)) {
								return;
							}
							onUpload(e);
						}
					}
				})
			},
			{
				char: '$',
				render: getSuggestionRenderer(CommandSuggestionList, {
					i18n,
					onSelect: (e) => {
						document.getElementById('chat-input')?.focus();
					},

					insertTextHandler: insertTextAtCursor,
					onUpload: () => {}
				})
			},
			{
				char: ':',
				allowSpaces: false,
				command: ({ editor, range, props }) => {
					// Convert the Unicode hex codepoint (e.g. "1F44B") to the actual emoji character (👋)
					const codepoint = props.id;
					const emoji = String.fromCodePoint(parseInt(codepoint, 16));
					editor.chain().focus().deleteRange(range).insertContent(emoji).run();
				},
				render: getSuggestionRenderer(CommandSuggestionList, {
					i18n,
					onSelect: (e) => {
						document.getElementById('chat-input')?.focus();
					},

					insertTextHandler: insertTextAtCursor,
					onUpload: () => {}
				})
			}
		];
		loaded = true;

		window.setTimeout(() => {
			const chatInput = document.getElementById('chat-input');
			chatInput?.focus();
		}, 0);

		window.addEventListener('keydown', onKeyDown);
		window.addEventListener('keyup', onKeyUp);

		window.addEventListener('focus', onFocus);
		window.addEventListener('blur', onBlur);

		let isDestroyed = false;
		let dropzoneElement: HTMLElement | null = null;
		const initialize = async () => {
			await tick();
			if (isDestroyed) return;

			dropzoneElement = document.getElementById('chat-pane');
			if (dropzoneElement) {
				dropzoneElement.addEventListener('dragover', onDragOver, true);
				dropzoneElement.addEventListener('drop', onDrop, true);
				dropzoneElement.addEventListener('dragleave', onDragLeave);
			}

			tools.set(await getTools(localStorage.token));
		};
		initialize();

		return () => {
			isDestroyed = true;

			window.removeEventListener('keydown', onKeyDown);
			window.removeEventListener('keyup', onKeyUp);

			window.removeEventListener('focus', onFocus);
			window.removeEventListener('blur', onBlur);

			if (dropzoneElement) {
				dropzoneElement.removeEventListener('dragover', onDragOver, true);
				dropzoneElement.removeEventListener('drop', onDrop, true);
				dropzoneElement.removeEventListener('dragleave', onDragLeave);
			}
		};
	});
</script>

<ToolServersModal bind:show={showTools} {selectedToolIds} />

<InputVariablesModal
	bind:show={showInputVariablesModal}
	variables={inputVariables}
	onSave={inputVariablesModalCallback}
/>

<ValvesModal
	bind:show={showValvesModal}
	userValves={true}
	type={selectedValvesType}
	id={selectedValvesItemId ?? null}
	on:save={async () => {
		await tick();
	}}
	on:close={() => {
		integrationsMenuCloseOnOutsideClick = true;
	}}
/>

<InputModal
	bind:show={showInputModal}
	bind:value={prompt}
	bind:inputContent
	onChange={(content) => {
		console.log(content);
		chatInputElement?.setContent(content?.json ?? null);
	}}
	onClose={async () => {
		await tick();
		chatInputElement?.focus();
	}}
/>

{#if loaded}
	<div class="w-full font-primary">
		<div class=" mx-auto inset-x-0 bg-transparent flex justify-center">
			<div
				class="flex flex-col px-3 {($settings?.widescreenMode ?? null)
					? 'max-w-full'
					: 'max-w-6xl'} w-full"
			>
				<div class="relative">
					{#if autoScroll === false && history?.currentId}
						<div
							class=" absolute -top-12 left-0 right-0 flex justify-center z-30 pointer-events-none"
						>
							<button
								class=" bg-white border border-gray-100 dark:border-none dark:bg-white/20 p-1.5 rounded-full pointer-events-auto"
								on:click={() => {
									autoScroll = true;
									scrollToBottom();
								}}
							>
								<svg
									xmlns="http://www.w3.org/2000/svg"
									viewBox="0 0 20 20"
									fill="currentColor"
									class="w-5 h-5"
								>
									<path
										fill-rule="evenodd"
										d="M10 3a.75.75 0 01.75.75v10.638l3.96-4.158a.75.75 0 111.08 1.04l-5.25 5.5a.75.75 0 01-1.08 0l-5.25-5.5a.75.75 0 111.08-1.04l3.96 4.158V3.75A.75.75 0 0110 3z"
										clip-rule="evenodd"
									/>
								</svg>
							</button>
						</div>
					{/if}
				</div>
			</div>
		</div>

		<div class="bg-transparent">
			<div
				class="{($settings?.widescreenMode ?? null)
					? 'max-w-full'
					: 'max-w-6xl'} px-2.5 mx-auto inset-x-0"
			>
				<div class="">
					<input
						bind:this={filesInputElement}
						bind:files={inputFiles}
						type="file"
						hidden
						multiple
						on:change={async () => {
							if (inputFiles && inputFiles.length > 0) {
								const _inputFiles = Array.from(inputFiles);
								inputFilesHandler(_inputFiles);
							} else {
								toast.error($i18n.t(`File not found.`));
							}

							filesInputElement.value = '';
						}}
					/>


							<form
							class="w-full flex flex-col gap-1.5"
							on:submit|preventDefault={() => {
								// check if selectedModels support image input
								dispatch('submit', prompt);
							}}
						>
						<button
							id="generate-message-pair-button"
							class="hidden"
							on:click={() => createMessagePair(prompt)}
						/>

						<!-- Task list display -->
						{#if isActive && chatTasks.length > 0}
							<div class="mx-1">
								<TaskList tasks={chatTasks} />
							</div>
						{/if}

						<!-- Queued messages display -->
						{#if messageQueue.length > 0}
							<div
								class="mb-1 mx-2 py-0.5 px-1.5 rounded-2xl bg-white dark:bg-gray-900/60 border border-gray-100 dark:border-gray-800/50 overflow-x-hidden overflow-y-auto max-h-[25vh]"
							>
								{#each messageQueue as queuedMessage (queuedMessage.id)}
									<QueuedMessageItem
										id={queuedMessage.id}
										content={queuedMessage.prompt}
										files={queuedMessage.files}
										onSendNow={onQueueSendNow}
										onEdit={onQueueEdit}
										onDelete={onQueueDelete}
									/>
								{/each}
							</div>
						{/if}

							<div
								id="message-input-container"
								class="flex items-center gap-2 rounded-full border border-neutral-200 dark:border-neutral-800 bg-white dark:bg-neutral-900 px-3 py-2 shadow-[0_0_40px_rgba(0,0,0,0.04)] dark:shadow-none"
								dir={$settings?.chatDirection ?? 'auto'}
							>
								{#if !$mobile}
									<button
										type="button"
										aria-label="Dodaj"
										on:click={() => (openPlusMenu = true)}
										data-plus-trigger
										class="flex h-9 w-9 shrink-0 items-center justify-center rounded-full text-neutral-700 dark:text-neutral-200 hover:bg-neutral-100 dark:hover:bg-neutral-800 transition-colors"
									>
										<Plus class="h-5 w-5" strokeWidth={2} />
									</button>

									{#if openPlusMenu}
										<div
											id="plus-menu"
											class="absolute bottom-20 left-3 z-50 min-w-[180px] rounded-2xl border border-neutral-200 dark:border-neutral-700 bg-white dark:bg-neutral-900 p-1.5 shadow-xl animate-in fade-in slide-in-from-bottom-2 duration-150"
										>
											<button
												type="button"
												on:click={() => handlePlusPick('camera')}
												class="w-full flex items-center gap-3 rounded-xl px-3 py-2.5 text-sm text-neutral-800 dark:text-neutral-100 cursor-pointer hover:bg-neutral-100 dark:hover:bg-neutral-800 focus:bg-neutral-100 dark:focus:bg-neutral-800 outline-none transition-colors"
											>
												<span
													class="inline-flex h-5 w-5 items-center justify-center text-neutral-500 dark:text-neutral-400"
													>{@html CAMERA_ICON}</span
												>
												Aparat
											</button>
											<button
												type="button"
												on:click={() => handlePlusPick('photos')}
												class="w-full flex items-center gap-3 rounded-xl px-3 py-2.5 text-sm text-neutral-800 dark:text-neutral-100 cursor-pointer hover:bg-neutral-100 dark:hover:bg-neutral-800 focus:bg-neutral-100 dark:focus:bg-neutral-800 outline-none transition-colors"
											>
												<span
													class="inline-flex h-5 w-5 items-center justify-center text-neutral-500 dark:text-neutral-400"
													>{@html PHOTO_ICON}</span
												>
												Zdjęcia
											</button>
											<button
												type="button"
												on:click={() => handlePlusPick('files')}
												class="w-full flex items-center gap-3 rounded-xl px-3 py-2.5 text-sm text-neutral-800 dark:text-neutral-100 cursor-pointer hover:bg-neutral-100 dark:hover:bg-neutral-800 focus:bg-neutral-100 dark:focus:bg-neutral-800 outline-none transition-colors"
											>
												<span
													class="inline-flex h-5 w-5 items-center justify-center text-neutral-500 dark:text-neutral-400"
													>{@html FILE_ICON}</span
												>
												Pliki
											</button>
											<button
												type="button"
												on:click={() => {
													webSearchEnabled = !webSearchEnabled;
													openPlusMenu = false;
												}}
												class="w-full flex items-center gap-3 rounded-xl px-3 py-2.5 text-sm {webSearchEnabled
													? 'text-blue-500'
													: 'text-neutral-800 dark:text-neutral-100'} cursor-pointer hover:bg-neutral-100 dark:hover:bg-neutral-800 focus:bg-neutral-100 dark:focus:bg-neutral-800 outline-none transition-colors"
											>
												<span
													class="inline-flex h-5 w-5 items-center justify-center {webSearchEnabled
														? 'text-blue-500'
														: 'text-neutral-500 dark:text-neutral-400'}"
												>
													<Globe class="h-5 w-5" strokeWidth={1.75} />
												</span>
												Web search
											</button>
										</div>
									{/if}
								{/if}

								{#if $mobile}
									<button
										type="button"
										aria-label="Dodaj"
										on:click={() => (openPlusMenu = true)}
										class="flex h-9 w-9 shrink-0 items-center justify-center rounded-full text-neutral-700 dark:text-neutral-200 hover:bg-neutral-100 dark:hover:bg-neutral-800 transition-colors"
									>
										<Plus class="h-5 w-5" strokeWidth={2} />
									</button>
								{/if}

								<div class="flex-1">
							{#if atSelectedModel !== undefined}
								<div class="px-3 pt-3 text-left w-full flex flex-col z-10">
									<div class="flex items-center justify-between w-full">
										<div class="pl-[1px] flex items-center gap-2 text-sm dark:text-gray-500">
											<img
												alt="model profile"
												class="size-3.5 max-w-[28px] object-cover rounded-full"
												src={`${WEBUI_API_BASE_URL}/models/model/profile/image?id=${$models.find((model) => model.id === atSelectedModel.id).id}&lang=${$i18n.language}`}
											/>
											<div class="translate-y-[0.5px]">
												<span class="">{atSelectedModel.name}</span>
											</div>
										</div>
										<div>
											<button
												class="flex items-center dark:text-gray-500"
												on:click={() => {
													atSelectedModel = undefined;
												}}
											>
												<XMark />
											</button>
										</div>
									</div>
								</div>
							{/if}

							{#if files.length > 0}
								<div
									class="mx-2 mt-2.5 pb-1.5 flex items-center flex-wrap gap-2"
									dir={$settings?.chatDirection ?? 'auto'}
								>
									{#each files as file, fileIdx}
										{#if file.type === 'image' || (file?.content_type ?? '').startsWith('image/')}
											{@const fileUrl =
												file.url.startsWith('data') || file.url.startsWith('http')
													? file.url
													: `${WEBUI_API_BASE_URL}/files/${file.url}${file?.content_type ? '/content' : ''}`}
											<div class=" relative group">
												<div class="relative flex items-center">
													<Image
														src={fileUrl}
														alt=""
														imageClassName=" size-10 rounded-xl object-cover"
													/>
													{#if atSelectedModel ? visionCapableModels.length === 0 : selectedModels.length !== visionCapableModels.length}
														<Tooltip
															className=" absolute top-1 left-1"
															content={$i18n.t('{{ models }}', {
																models: [...(atSelectedModel ? [atSelectedModel] : selectedModels)]
																	.filter((id) => !visionCapableModels.includes(id))
																	.join(', ')
															})}
														>
															<svg
																xmlns="http://www.w3.org/2000/svg"
																viewBox="0 0 24 24"
																fill="currentColor"
																aria-hidden="true"
																class="size-4 fill-yellow-300"
															>
																<path
																	fill-rule="evenodd"
																	d="M9.401 3.003c1.155-2 4.043-2 5.197 0l7.355 12.748c1.154 2-.29 4.5-2.599 4.5H4.645c-2.309 0-3.752-2.5-2.598-4.5L9.4 3.003ZM12 8.25a.75.75 0 0 1 .75.75v3.75a.75.75 0 0 1-1.5 0V9a.75.75 0 0 1 .75-.75Zm0 8.25a.75.75 0 1 0 0-1.5.75.75 0 0 0 0 1.5Z"
																	clip-rule="evenodd"
																/>
															</svg>
														</Tooltip>
													{/if}
												</div>
												<div class=" absolute -top-1 -right-1">
													<button
														class=" bg-white text-black border border-white rounded-full {($settings?.highContrastMode ??
														false)
															? ''
															: 'outline-hidden focus:outline-hidden group-hover:visible invisible transition'}"
														type="button"
														aria-label={$i18n.t('Remove file')}
														on:click={() => {
															files.splice(fileIdx, 1);
															files = files;
														}}
													>
														<svg
															xmlns="http://www.w3.org/2000/svg"
															viewBox="0 0 20 20"
															fill="currentColor"
															aria-hidden="true"
															class="size-4"
														>
															<path
																d="M6.28 5.22a.75.75 0 00-1.06 1.06L8.94 10l-3.72 3.72a.75.75 0 101.06 1.06L10 11.06l3.72 3.72a.75.75 0 101.06-1.06L11.06 10l3.72-3.72a.75.75 0 00-1.06-1.06L10 8.94 6.28 5.22z"
															/>
														</svg>
													</button>
												</div>
											</div>
										{:else}
											<FileItem
												item={file}
												name={file.name}
												type={file.type}
												size={file?.size}
												loading={file.status === 'uploading'}
												dismissible={true}
												edit={true}
												small={true}
												modal={['file', 'collection'].includes(file?.type)}
												on:dismiss={async () => {
													// Remove from UI state
													files.splice(fileIdx, 1);
													files = files;
												}}
												on:click={() => {
													console.log(file);
												}}
											/>
										{/if}
									{/each}
								</div>
							{/if}

							<div class="px-2.5">
								<div
									class="scrollbar-hidden rtl:text-right ltr:text-left bg-transparent dark:text-gray-100 outline-hidden w-full pb-1 px-1 resize-none h-fit max-h-96 overflow-auto {files.length ===
									0
										? atSelectedModel !== undefined
											? 'pt-1.5'
											: 'pt-2.5'
										: ''}"
									id="chat-input-container"
								>
									{#if prompt.split('\n').length > 2}
										<div class="fixed top-0 right-0 z-20">
											<div class="mt-2.5 mr-3">
												<button
													type="button"
													class="p-1 rounded-lg hover:bg-gray-100/50 dark:hover:bg-gray-800/50"
													aria-label="Expand input"
													on:click={async () => {
														showInputModal = true;
													}}
												>
													<Expand />
												</button>
											</div>
										</div>
									{/if}

									{#if suggestions}
										{#key $settings?.richTextInput ?? true}
											{#key $settings?.showFormattingToolbar ?? false}
												<RichTextInput
													bind:this={chatInputElement}
													id="chat-input"
													editable={!showInputModal}
													onChange={(content) => {
														prompt = content.md;
														inputContent = content;
														command = getCommand();
													}}
													json={true}
													richText={$settings?.richTextInput ?? true}
													messageInput={true}
													showFormattingToolbar={$settings?.showFormattingToolbar ?? false}
													floatingMenuPlacement={'top-start'}
													insertPromptAsRichText={$settings?.insertPromptAsRichText ?? false}
													shiftEnter={!($settings?.ctrlEnterToSend ?? false) &&
														!$mobile &&
														!(
															'ontouchstart' in window ||
															navigator.maxTouchPoints > 0 ||
															navigator.msMaxTouchPoints > 0
														)}
														placeholder={placeholder ? placeholder : 'Zapytaj o cokolwiek'}
													largeTextAsFile={($settings?.largeTextAsFile ?? false) && !shiftKey}
													autocomplete={$config?.features?.enable_autocomplete_generation &&
														($settings?.promptAutocomplete ?? false)}
													generateAutoCompletion={async (text) => {
														if (selectedModelIds.length === 0 || !selectedModelIds.at(0)) {
															toast.error($i18n.t('Please select a model first.'));
														}

														const res = await generateAutoCompletion(
															localStorage.token,
															selectedModelIds.at(0),
															text,
															history?.currentId
																? createMessagesList(history, history.currentId)
																: null
														).catch((error) => {
															console.log(error);

															return null;
														});

														console.log(res);
														return res;
													}}
													{suggestions}
													oncompositionstart={() => (isComposing = true)}
													oncompositionend={(e) => {
														compositionEndedAt = e.timeStamp;
														isComposing = false;
													}}
													on:keydown={async (e) => {
														e = e.detail.event;

														const isCtrlPressed = e.ctrlKey || e.metaKey; // metaKey is for Cmd key on Mac
														const suggestionsContainerElement =
															document.getElementById('suggestions-container');

														if (e.key === 'Escape') {
															stopResponse();
														}

														if (prompt === '' && e.key == 'ArrowUp') {
															e.preventDefault();

															const userMessageElement = [
																...document.getElementsByClassName('user-message')
															]?.at(-1);

															if (userMessageElement) {
																userMessageElement.scrollIntoView({ block: 'center' });
																const editButton = [
																	...document.getElementsByClassName('edit-user-message-button')
																]?.at(-1);

																editButton?.click();
															}
														}

														if (!suggestionsContainerElement) {
															if (
																!$mobile ||
																!(
																	'ontouchstart' in window ||
																	navigator.maxTouchPoints > 0 ||
																	navigator.msMaxTouchPoints > 0
																)
															) {
																if (inOrNearComposition(e)) {
																	return;
																}

																// Uses keyCode '13' for Enter key for chinese/japanese keyboards.
																//
																// Depending on the user's settings, it will send the message
																// either when Enter is pressed or when Ctrl+Enter is pressed.
																const enterPressed =
																	($settings?.ctrlEnterToSend ?? false)
																		? (e.key === 'Enter' || e.keyCode === 13) && isCtrlPressed
																		: (e.key === 'Enter' || e.keyCode === 13) && !e.shiftKey;

																if (enterPressed) {
																	e.preventDefault();
																	if (prompt !== '' || files.length > 0) {
																		dispatch('submit', prompt);
																	}
																}
															}
														}

														if (e.key === 'Escape') {
															console.log('Escape');
															atSelectedModel = undefined;
															selectedToolIds = [];
															selectedFilterIds = [];

																webSearchEnabled = false;
																imageGenerationEnabled = false;
															}
													}}
													on:paste={async (e) => {
														e = e.detail.event;
														console.log(e);

														const clipboardData = e.clipboardData || window.clipboardData;

														if (clipboardData && clipboardData.items) {
															for (const item of clipboardData.items) {
																if (item.type === 'text/plain') {
																	if (($settings?.largeTextAsFile ?? false) && !shiftKey) {
																		const text = clipboardData.getData('text/plain');

																		if (text.length > PASTED_TEXT_CHARACTER_LIMIT) {
																			e.preventDefault();
																			const blob = new Blob([text], { type: 'text/plain' });
																			const file = new File(
																				[blob],
																				`Pasted_Text_${Date.now()}.txt`,
																				{
																					type: 'text/plain'
																				}
																			);

																			await uploadFileHandler(file, true, { context: 'full' });
																		}
																	}
																} else {
																	const file = item.getAsFile();
																	if (file) {
																		await inputFilesHandler([file]);
																		e.preventDefault();
																	}
																}
															}
														}
													}}
												/>
											{/key}
										{/key}
									{/if}
								</div>
							</div>

							<div class=" flex justify-between mt-0.5 mb-2.5 mx-0.5 max-w-full" dir="ltr">
								<div class="ml-1 self-end flex items-center flex-1 max-w-[80%]">
									<InputMenu
										bind:files
										selectedModels={atSelectedModel ? [atSelectedModel.id] : selectedModels}
										{fileUploadCapableModels}
										{screenCaptureHandler}
										{inputFilesHandler}
										uploadFilesHandler={() => {
											filesInputElement.click();
										}}
										uploadGoogleDriveHandler={async () => {
											try {
												const fileData = await createPicker();
												if (fileData) {
													const file = new File([fileData.blob], fileData.name, {
														type: fileData.blob.type
													});
													await uploadFileHandler(file);
												} else {
													console.log('No file was selected from Google Drive');
												}
											} catch (error) {
												console.error('Google Drive Error:', error);
												toast.error(
													$i18n.t('Error accessing Google Drive: {{error}}', {
														error: error.message
													})
												);
											}
										}}
										uploadOneDriveHandler={async (authorityType) => {
											try {
												const fileData = await pickAndDownloadFile(authorityType);
												if (fileData) {
													const file = new File([fileData.blob], fileData.name, {
														type: fileData.blob.type || 'application/octet-stream'
													});
													await uploadFileHandler(file);
												} else {
													console.log('No file was selected from OneDrive');
												}
											} catch (error) {
												console.error('OneDrive Error:', error);
											}
										}}
										{onUpload}
										onClose={async () => {
											await tick();

											const chatInput = document.getElementById('chat-input');
											chatInput?.focus();
										}}
									>
										<div
											id="input-menu-button"
											class="bg-transparent hover:bg-gray-100 text-gray-700 dark:text-white dark:hover:bg-gray-800 rounded-full size-8 flex justify-center items-center outline-hidden focus:outline-hidden"
										>
											<PlusAlt className="size-5.5" />
										</div>
									</InputMenu>

									{#if showWebSearchButton || showImageGenerationButton || showCodeInterpreterButton || showToolsButton || (toggleFilters && toggleFilters.length > 0)}
										<div
											class="flex self-center w-[1px] h-4 mx-1 bg-gray-200/50 dark:bg-gray-800/50"
										/>

										<IntegrationsMenu
											selectedModels={atSelectedModel ? [atSelectedModel.id] : selectedModels}
											{toggleFilters}
											{showWebSearchButton}
											{showImageGenerationButton}
											{showCodeInterpreterButton}
											bind:selectedToolIds
											bind:selectedFilterIds
											bind:webSearchEnabled
											bind:imageGenerationEnabled
											bind:codeInterpreterEnabled
											closeOnOutsideClick={integrationsMenuCloseOnOutsideClick}
											onShowValves={(e) => {
												const { type, id } = e;
												selectedValvesType = type;
												selectedValvesItemId = id;
												showValvesModal = true;
												integrationsMenuCloseOnOutsideClick = false;
											}}
											onClose={async () => {
												await tick();

												const chatInput = document.getElementById('chat-input');
												chatInput?.focus();
											}}
										>
											<div
												id="integration-menu-button"
												class="bg-transparent hover:bg-gray-100 text-gray-700 dark:text-white dark:hover:bg-gray-800 rounded-full size-8 flex justify-center items-center outline-hidden focus:outline-hidden"
											>
												<Component className="size-4.5" strokeWidth="1.5" />
											</div>
										</IntegrationsMenu>
									{/if}

									{#if selectedModelIds.length === 1 && $models.find((m) => m.id === selectedModelIds[0])?.has_user_valves}
										<div class="ml-1 flex gap-1.5">
											<Tooltip content={$i18n.t('Valves')} placement="top">
												<button
													type="button"
													id="model-valves-button"
													class="bg-transparent hover:bg-gray-100 text-gray-700 dark:text-white dark:hover:bg-gray-800 rounded-full size-8 flex justify-center items-center outline-hidden focus:outline-hidden"
													on:click={() => {
														selectedValvesType = 'function';
														selectedValvesItemId = selectedModelIds[0]?.split('.')[0];
														showValvesModal = true;
													}}
												>
													<Knobs className="size-4" strokeWidth="1.5" />
												</button>
											</Tooltip>
										</div>
									{/if}

									<div class="ml-1 flex gap-1.5">
										{#if (selectedToolIds ?? []).length > 0}
											<Tooltip
												content={$i18n.t('{{COUNT}} Available Tools', {
													COUNT: (selectedToolIds ?? []).length
												})}
											>
												<button
													class="translate-y-[0.5px] px-1 flex gap-1 items-center text-gray-600 dark:text-gray-300 hover:text-gray-700 dark:hover:text-gray-200 rounded-lg self-center transition"
													aria-label="Available Tools"
													type="button"
													on:click={() => {
														showTools = !showTools;
													}}
												>
													<Wrench className="size-4" strokeWidth="1.75" />

													<span class="text-sm">
														{(selectedToolIds ?? []).length}
													</span>
												</button>
											</Tooltip>
										{/if}

										{#each selectedFilterIds as filterId (filterId)}
											{@const filter = toggleFilters.find((f) => f.id === filterId)}
											{#if filter}
												<Tooltip content={filter?.name} placement="top">
													<button
														on:click|preventDefault={() => {
															if (
																filter?.has_user_valves &&
																($_user?.role === 'admin' ||
																	($_user?.permissions?.chat?.valves ?? true))
															) {
																selectedValvesType = 'function';
																selectedValvesItemId = filterId;
																showValvesModal = true;
															} else {
																selectedFilterIds = selectedFilterIds.filter(
																	(id) => id !== filterId
																);
															}
														}}
														type="button"
														class="group p-[7px] flex gap-1.5 items-center text-sm rounded-full transition-colors duration-300 focus:outline-hidden max-w-full overflow-hidden {selectedFilterIds.includes(
															filterId
														)
															? 'text-sky-500 dark:text-sky-300 bg-sky-50 hover:bg-sky-100 dark:bg-sky-400/10 dark:hover:bg-sky-600/10 border border-sky-200/40 dark:border-sky-500/20'
															: 'bg-transparent text-gray-600 dark:text-gray-300 hover:bg-gray-50 dark:hover:bg-gray-800 '} capitalize"
													>
														{#if filter?.icon}
															<div class="size-4 items-center flex justify-center">
																<img
																	src={filter.icon}
																	class="size-3.5 {filter.icon.includes('data:image/svg')
																		? 'dark:invert-[80%]'
																		: ''}"
																	style="fill: currentColor;"
																	alt={filter.name}
																/>
															</div>
														{:else}
															<Sparkles className="size-4" strokeWidth="1.75" />
														{/if}
														<!-- svelte-ignore a11y-click-events-have-key-events -->
														<!-- svelte-ignore a11y-no-static-element-interactions -->
														<div
															class="hidden group-hover:block"
															on:click={(e) => {
																e.stopPropagation();
																e.preventDefault();
																selectedFilterIds = selectedFilterIds.filter(
																	(id) => id !== filterId
																);
															}}
														>
															<XMark className="size-4" strokeWidth="1.75" />
														</div>
													</button>
												</Tooltip>
											{/if}
										{/each}

										{#if webSearchEnabled}
											<Tooltip content={$i18n.t('Web Search')} placement="top">
												<button
													on:click|preventDefault={() => (webSearchEnabled = !webSearchEnabled)}
													type="button"
													class="group p-[7px] flex gap-1.5 items-center text-sm rounded-full transition-colors duration-300 focus:outline-hidden max-w-full overflow-hidden {webSearchEnabled ||
													($settings?.webSearch ?? false) === 'always'
														? ' text-sky-500 dark:text-sky-300 bg-sky-50 hover:bg-sky-100 dark:bg-sky-400/10 dark:hover:bg-sky-600/10 border border-sky-200/40 dark:border-sky-500/20'
														: 'bg-transparent text-gray-600 dark:text-gray-300 hover:bg-gray-50 dark:hover:bg-gray-800 '}"
												>
													<GlobeAlt className="size-4" strokeWidth="1.75" />
													<div class="hidden group-hover:block">
														<XMark className="size-4" strokeWidth="1.75" />
													</div>
												</button>
											</Tooltip>
										{/if}

										{#if imageGenerationEnabled}
											<Tooltip content={$i18n.t('Image')} placement="top">
												<button
													on:click|preventDefault={() =>
														(imageGenerationEnabled = !imageGenerationEnabled)}
													type="button"
													class="group p-[7px] flex gap-1.5 items-center text-sm rounded-full transition-colors duration-300 focus:outline-hidden max-w-full overflow-hidden {imageGenerationEnabled
														? ' text-sky-500 dark:text-sky-300 bg-sky-50 hover:bg-sky-100 dark:bg-sky-400/10 dark:hover:bg-sky-700/10 border border-sky-200/40 dark:border-sky-500/20'
														: 'bg-transparent text-gray-600 dark:text-gray-300 hover:bg-gray-50 dark:hover:bg-gray-800 '}"
												>
													<Photo className="size-4" strokeWidth="1.75" />
													<div class="hidden group-hover:block">
														<XMark className="size-4" strokeWidth="1.75" />
													</div>
												</button>
											</Tooltip>
										{/if}

										{#if codeInterpreterEnabled}
											<Tooltip content={$i18n.t('Code Interpreter')} placement="top">
												<button
													aria-label={codeInterpreterEnabled
														? $i18n.t('Disable Code Interpreter')
														: $i18n.t('Enable Code Interpreter')}
													aria-pressed={codeInterpreterEnabled}
													on:click|preventDefault={() =>
														(codeInterpreterEnabled = !codeInterpreterEnabled)}
													type="button"
													class=" group p-[7px] flex gap-1.5 items-center text-sm transition-colors duration-300 max-w-full overflow-hidden {codeInterpreterEnabled
														? ' text-sky-500 dark:text-sky-300 bg-sky-50 hover:bg-sky-100 dark:bg-sky-400/10 dark:hover:bg-sky-700/10 border border-sky-200/40 dark:border-sky-500/20'
														: 'bg-transparent text-gray-600 dark:text-gray-300 hover:bg-gray-50 dark:hover:bg-gray-800 '} {($settings?.highContrastMode ??
													false)
														? 'm-1'
														: 'focus:outline-hidden rounded-full'}"
												>
													<Terminal className="size-3.5" strokeWidth="2" />

													<div class="hidden group-hover:block">
														<XMark className="size-4" strokeWidth="1.75" />
													</div>
												</button>
											</Tooltip>
										{/if}

										{#each pendingOAuthTools as pendingTool (pendingTool.id)}
											<Tooltip content={$i18n.t('Click to connect')} placement="top">
												<button
													on:click|preventDefault={() => {
														sessionStorage.setItem('pendingOAuthToolId', pendingTool.id);
														const authUrl = getOAuthClientAuthorizationUrl(
															pendingTool.serverId,
															pendingTool.authType ?? 'mcp'
														);
														window.open(authUrl, '_self', 'noopener');
													}}
													type="button"
													class="group px-2 py-[5px] flex gap-1.5 items-center text-xs rounded-full transition-colors duration-300 focus:outline-hidden max-w-full overflow-hidden
														text-amber-600 dark:text-amber-400 bg-amber-50 hover:bg-amber-100 dark:bg-amber-400/10 dark:hover:bg-amber-600/10 border border-amber-200/40 dark:border-amber-500/20"
												>
													<Wrench className="size-3.5" strokeWidth="1.75" />
													<span class="truncate">{pendingTool.name}</span>
												</button>
											</Tooltip>
										{/each}
									</div>
								</div>

								<div class="self-end flex space-x-1 mr-1 shrink-0 gap-[0.5px]">
									{#if isActive && prompt === '' && files.length === 0}
										<div class=" flex items-center">
											<Tooltip content={$i18n.t('Stop')}>
												<button
													class="bg-white hover:bg-gray-100 text-gray-800 dark:bg-gray-700 dark:text-white dark:hover:bg-gray-800 transition rounded-full p-1.5"
													on:click={() => {
														stopResponse();
													}}
												>
													<svg
														xmlns="http://www.w3.org/2000/svg"
														viewBox="0 0 24 24"
														fill="currentColor"
														class="size-5"
													>
														<path
															fill-rule="evenodd"
															d="M2.25 12c0-5.385 4.365-9.75 9.75-9.75s9.75 4.365 9.75 9.75-4.365 9.75-9.75 9.75S2.25 17.385 2.25 12zm6-2.438c0-.724.588-1.312 1.313-1.312h4.874c.725 0 1.313.588 1.313 1.313v4.874c0 .725-.588 1.313-1.313 1.313H9.564a1.312 1.312 0 01-1.313-1.313V9.564z"
															clip-rule="evenodd"
														/>
													</svg>
												</button>
											</Tooltip>
										</div>
									{:else}
										{#if prompt !== '' && !history?.currentId && !$selectedTerminalId && ($config?.features?.enable_notes ?? false) && ($_user?.role === 'admin' || ($_user?.permissions?.features?.notes ?? true))}
											<!-- {$i18n.t('Create Note')}  -->
											<Tooltip content={$i18n.t('Create note')} className=" flex items-center">
												<button
													id="create-note-button"
													class=" text-gray-500 dark:text-gray-500 hover:text-gray-700 dark:hover:text-gray-200 transition rounded-full p-1.5 -mr-1 self-center"
													type="button"
													disabled={prompt === '' && files.length === 0}
													on:click={() => {
														createNote();
													}}
												>
													<Note className="size-4.5 translate-y-[0.5px]" />
												</button>
											</Tooltip>
										{/if}

										{#if !history?.currentId || history.messages[history.currentId]?.done == true}
											<!-- Terminal Server Selector -->
											{@const hasDirectToolServerAccess =
												$_user?.role === 'admin' ||
												($_user?.permissions?.features?.direct_tool_servers ?? true)}
											{#if terminalCapableModels.length > 0 && (($terminalServers ?? []).some((t) => t.id) || (hasDirectToolServerAccess && (($terminalServers ?? []).some((t) => !t.id) || ($settings?.terminalServers ?? []).some((s) => s.url))))}
												<TerminalMenu bind:show={showTerminalMenu} />
											{/if}

											{/if}

											{#if !(prompt === '' && files.length === 0)}
											<div class=" flex items-center">
												<Tooltip
													content={uploadPending
														? $i18n.t('Waiting for upload...')
														: $i18n.t('Send message')}
												>
													<button
														id="send-message-button"
														class="{!(prompt === '' && files.length === 0) || uploadPending
															? 'bg-black text-white hover:bg-gray-900 dark:bg-white dark:text-black dark:hover:bg-gray-100 '
															: 'text-white bg-gray-200 dark:text-gray-900 dark:bg-gray-700 disabled'} transition rounded-full p-1.5 self-center"
														type="submit"
														disabled={(prompt === '' && files.length === 0) || uploadPending}
													>
														{#if uploadPending}
															<Spinner className="size-5" />
														{:else}
															<svg
																xmlns="http://www.w3.org/2000/svg"
																viewBox="0 0 16 16"
																fill="currentColor"
																class="size-5"
															>
																<path
																	fill-rule="evenodd"
																	d="M8 14a.75.75 0 0 1-.75-.75V4.56L4.03 7.78a.75.75 0 0 1-1.06-1.06l4.5-4.5a.75.75 0 0 1 1.06 0l4.5 4.5a.75.75 0 0 1-1.06 1.06L8.75 4.56v8.69A.75.75 0 0 1 8 14Z"
																	clip-rule="evenodd"
																/>
															</svg>
														{/if}
													</button>
												</Tooltip>
											</div>
										{/if}
									{/if}
								</div>
							</div>
						</div>

						{#if $config?.license_metadata?.input_footer}
							<div class=" text-xs text-gray-500 text-center line-clamp-1 marked">
								{@html DOMPurify.sanitize(marked($config?.license_metadata?.input_footer))}
							</div>
						{:else}
							<div class="mb-1" />
						{/if}
					</form>
				</div>
			</div>
		</div>
	</div>
{/if}
