const $ = (id) => document.getElementById(id);

let mode = "login";
let services = {};
let books = [];
let pollTimer = null;

async function api(path, options = {}) {
	const response = await fetch(path, {
		credentials: "same-origin",
		headers: options.body ? { "Content-Type": "application/json" } : {},
		...options,
	});
	let data = {};
	try {
		data = await response.json();
	} catch (e) {
		data = {};
	}
	return { status: response.status, ok: response.ok, data };
}

function message(text, kind = "") {
	const box = $("servicemsg");
	box.textContent = text || "";
	box.style.color = kind === "error" ? "var(--err)" : kind === "ok" ? "var(--ok)" : "";
}

function showAuth(show) {
	$("authview").classList.toggle("hidden", !show);
	$("appview").classList.toggle("hidden", show);
	$("userbox").classList.toggle("hidden", show);
}

async function boot() {
	const me = await api("/api/me");
	if (me.ok && me.data.username) {
		await startapp(me.data.username);
	} else {
		showAuth(true);
	}
}

async function startapp(username) {
	$("username").textContent = username;
	showAuth(false);
	const res = await api("/api/services");
	if (res.ok) {
		services = res.data.services;
		fillServices();
	}
	await refreshTokens();
	await refreshBooks();
}

function fillServices() {
	const select = $("service");
	select.innerHTML = "";
	for (const [code, label] of Object.entries(services)) {
		const option = document.createElement("option");
		option.value = code;
		option.textContent = label;
		select.appendChild(option);
	}
	select.onchange = refreshTokens;
}

function servicename() {
	return services[$("service").value] || $("service").value;
}

async function refreshTokens() {
	const res = await api("/api/tokens");
	const badge = $("tokenstatus");
	if (!res.ok) return;
	const token = res.data.tokens.find((t) => t.service === $("service").value);
	if (token && token.saved) {
		badge.textContent = "login salvato sul server";
		badge.className = "badge ok";
	} else {
		badge.textContent = "nessun login salvato";
		badge.className = "badge warn";
	}
}

async function loadLibrary() {
	message("Carico la libreria…");
	$("librarymsg").textContent = "Carico la libreria…";
	const res = await api("/api/library?service=" + encodeURIComponent($("service").value));
	if (res.status === 409) {
		message("Fai prima il login al servizio: le credenziali vengono salvate sul server.", "error");
		$("librarymsg").textContent = "Login al servizio richiesto.";
		books = [];
		renderLibrary();
		return;
	}
	if (!res.ok) {
		message(res.data.error || "libreria non disponibile", "error");
		$("librarymsg").textContent = "Libreria non disponibile.";
		return;
	}
	books = res.data.books;
	message("");
	$("librarymsg").textContent = books.length + " libri trovati.";
	renderLibrary();
}

function renderLibrary() {
	const body = $("library").querySelector("tbody");
	body.innerHTML = "";
	for (const book of books) {
		const row = document.createElement("tr");
		const check = document.createElement("td");
		check.className = "check";
		const box = document.createElement("input");
		box.type = "checkbox";
		box.value = book.id;
		check.appendChild(box);
		const id = document.createElement("td");
		id.textContent = book.id;
		const title = document.createElement("td");
		title.textContent = book.title;
		row.append(check, id, title);
		body.appendChild(row);
	}
	$("downloadselected").disabled = books.length === 0;
	$("downloadall").disabled = books.length === 0;
}

async function refreshBooks() {
	const res = await api("/api/books");
	if (!res.ok) return;
	const list = res.data.books;
	const body = $("books").querySelector("tbody");
	body.innerHTML = "";
	for (const book of list) {
		const row = document.createElement("tr");
		const cells = [
			services[book.service] || book.service,
			book.title,
			String(book.pages),
			(book.size / 1024 / 1024).toFixed(1) + " MB",
		];
		for (const value of cells) {
			const cell = document.createElement("td");
			cell.textContent = value;
			row.appendChild(cell);
		}
		const action = document.createElement("td");
		const link = document.createElement("a");
		link.href = "/api/file/" + book.id;
		link.textContent = "Scarica PDF";
		action.appendChild(link);
		row.appendChild(action);
		body.appendChild(row);
	}
	$("booksmsg").textContent = list.length ? "" : "Nessun libro scaricato.";
}

async function saveServiceLogin(event) {
	event.preventDefault();
	const username = $("serviceuser").value.trim();
	const password = $("servicepass").value;
	if (!username || !password) {
		message("Inserisci email e password del servizio.", "error");
		return;
	}
	message("Login su " + servicename() + "…");
	const res = await api("/api/tokens", {
		method: "POST",
		body: JSON.stringify({ service: $("service").value, username, password }),
	});
	if (!res.ok) {
		message(res.data.error || "login non riuscito", "error");
		return;
	}
	$("servicepass").value = "";
	message("Login salvato sul server.", "ok");
	await refreshTokens();
	await loadLibrary();
}

async function startDownload(ids) {
	if (!ids.length) return;
	const res = await api("/api/downloads", {
		method: "POST",
		body: JSON.stringify({ service: $("service").value, books: ids }),
	});
	if (res.status === 409) {
		message("Fai prima il login al servizio.", "error");
		return;
	}
	if (!res.ok) {
		message(res.data.error || "impossibile avviare il download", "error");
		return;
	}
	$("jobcard").classList.remove("hidden");
	message("");
	watchJob(res.data.job);
}

function watchJob(jobid) {
	clearInterval(pollTimer);
	const tick = async () => {
		const res = await api("/api/downloads/" + jobid);
		if (!res.ok) {
			clearInterval(pollTimer);
			return;
		}
		renderJob(res.data);
		if (res.data.state === "done") {
			clearInterval(pollTimer);
			await refreshBooks();
		}
	};
	tick();
	pollTimer = setInterval(tick, 1200);
}

function renderJob(job) {
	$("jobitems").innerHTML = "";
	for (const item of job.items) {
		const li = document.createElement("li");
		const top = document.createElement("div");
		top.className = "top";
		const name = document.createElement("span");
		name.textContent = item.title || item.bookid;
		const state = document.createElement("span");
		state.className = "state " + item.status;
		state.textContent =
			item.status === "done" ? "completato" :
			item.status === "error" ? "errore: " + item.error :
			item.status === "downloading" ? (item.message || item.progress + "%") :
			"in coda";
		top.append(name, state);
		const bar = document.createElement("div");
		bar.className = "bar " + (item.status === "error" ? "error" : item.status === "done" ? "done" : "");
		const fill = document.createElement("span");
		fill.style.width = item.progress + "%";
		bar.appendChild(fill);
		li.append(top, bar);
		$("jobitems").appendChild(li);
	}
}

$("authform").addEventListener("submit", async (event) => {
	event.preventDefault();
	const username = $("authuser").value.trim();
	const password = $("authpass").value;
	const res = await api("/api/" + (mode === "login" ? "login" : "register"), {
		method: "POST",
		body: JSON.stringify({ username, password }),
	});
	if (!res.ok) {
		alert(res.data.error || "operazione non riuscita");
		return;
	}
	$("authpass").value = "";
	await startapp(res.data.username);
});

$("authtoggle").addEventListener("click", (event) => {
	event.preventDefault();
	mode = mode === "login" ? "register" : "login";
	$("authtitle").textContent = mode === "login" ? "Accedi" : "Crea un account";
	$("authsubmit").textContent = mode === "login" ? "Accedi" : "Registrati";
	$("authtoggle").textContent = mode === "login" ? "Registrati" : "Accedi";
});

$("logout").addEventListener("click", async () => {
	await api("/api/logout", { method: "POST" });
	clearInterval(pollTimer);
	location.reload();
});

$("serviceform").addEventListener("submit", saveServiceLogin);
$("loadlibrary").addEventListener("click", loadLibrary);
$("downloadselected").addEventListener("click", () => {
	const ids = [...$("library").querySelectorAll("tbody input:checked")].map((box) => box.value);
	if (!ids.length) {
		alert("Seleziona almeno un libro.");
		return;
	}
	startDownload(ids);
});
$("downloadall").addEventListener("click", () => startDownload(books.map((book) => book.id)));

boot();
