import { WEBUI_API_BASE_URL } from '$lib/constants';

export const synthesizeOpenAISpeech = async (token: string, voice: string, text: string) => {
	let error = null;

	const res = await fetch(`${WEBUI_API_BASE_URL}/audio/speech`, {
		method: 'POST',
		headers: {
			Accept: 'audio/mpeg',
			'Content-Type': 'application/json',
			authorization: `Bearer ${token}`
		},
		body: JSON.stringify({
			voice,
			input: text
		})
	}).catch((err) => {
		error = err?.detail ?? err;
		console.error(err);
		return null;
	});

	if (error) {
		throw error;
	}

	if (!res?.ok) {
		const err = await res.json().catch(() => ({ detail: 'Failed to synthesize speech' }));
		throw err?.detail ?? err;
	}

	return res;
};


export const getVoices = async (token: string) => {
	let error = null;

	const res = await fetch(`${WEBUI_API_BASE_URL}/audio/voices`, {
		method: 'GET',
		headers: {
			Accept: 'application/json',
			'Content-Type': 'application/json',
			authorization: `Bearer ${token}`
		}
	})
		.then(async (res) => {
			if (!res.ok) throw await res.json();
			return res.json();
		})
		.catch((err) => {
			error = err?.detail ?? err;
			console.error(err);
			return null;
		});

	if (error) {
		throw error;
	}

	return res;
};
