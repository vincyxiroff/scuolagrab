import sys
import dependencies

if not dependencies.ensure():
	sys.exit(1)

import utils
import os
import re
from pathlib import Path
from rich.console import Console
from rich.table import Table
from rich.rule import Rule
from rich.panel import Panel
from rich import box
from rich.prompt import Prompt
from rich.prompt import Confirm
from rich.progress import Progress, BarColumn, TaskProgressColumn, TextColumn, TimeElapsedColumn
import config

console = Console()
userid = False

config = config.getconfig()

banner = """
  scuolagrab
  schoolbook downloader
"""

bookprompt = "Books to download (e.g. [cyan]0[/cyan], [cyan]0,3[/cyan], [cyan]2-5[/cyan] or [cyan]all[/cyan], empty to cancel)"

def center(var:str, space:int=None):
	'''center elements (text) in the terminal'''
	if space is None:
		try:
			space = os.get_terminal_size().columns
		except OSError:
			# Not attached to a terminal, don't bother centering
			return var
	middleline = var.splitlines()[len(var.splitlines()) // 2]
	return '\n'.join(' ' * int(max(space - len(middleline), 0) / 2) + line for line in var.splitlines())

def login():
	global userid
	checkpassword = config.getboolean("pdfgrabber", "AskPassword", fallback=False)
	users = utils.getusers()

	if not users:
		console.print("No scuolagrab users yet. Let's create one.", style="yellow")
		register()
		users = utils.getusers()

	username, password = "", ""
	if len(users) == 1 and not checkpassword:
		# No point in asking when there is only one user
		username = users[0]

	first = True
	while not (userid := utils.new_login(username, password, checkpassword)):
		if not first:
			console.print("Invalid login!", style="red")
		first = False
		if checkpassword:
			username = Prompt.ask("[b]scuolagrab[/b] username")
			password = Prompt.ask("[b]scuolagrab[/b] password", password=True)
		else:
			username = Prompt.ask("[b]scuolagrab[/b] username", choices=users, show_choices=False)
	console.print(f"Logged in as [bold]{username}[/bold]!", style="green")

def selectservice(services):
	table = Table(title="Available services", box=box.SIMPLE_HEAVY, title_justify="left")
	table.add_column("Code", style="bold cyan", justify="center")
	table.add_column("Service", style="green")

	for code, name in services.items():
		table.add_row(code, name)

	console.print(table)

	return Prompt.ask("Choose a service", choices=services.keys(), show_choices=False)

def managetokens():
	if not userid:
		login()
	table = Table(title="Saved tokens", box=box.SIMPLE_HEAVY, title_justify="left")
	table.add_column("Service", style="cyan")
	table.add_column("Token", style="green")

	saved = []
	for service in utils.services:
		token = utils.gettoken(userid, service)
		if token:
			saved.append(service)
		table.add_row(utils.services[service], token[:20] + "..." if token else "[dim]not saved[/dim]")

	console.print(table)

	if not saved:
		console.print("No tokens to delete.", style="yellow")
		return

	servicenow = Prompt.ask("Choose a service to delete the token from", choices=saved, show_choices=False)
	if not Confirm.ask(f"Delete the token for [bold]{utils.services[servicenow]}[/bold]?", default=False):
		console.print("Nothing deleted.", style="yellow")
		return
	utils.deletetoken(servicenow, userid)
	console.print(f"Token for [bold]{utils.services[servicenow]}[/bold] deleted!", style="green")

def downloadbook():
	global userid
	if not userid:
		login()

	service = selectservice(utils.services)
	token = utils.gettoken(userid, service)
	servicename = utils.services[service]

	if token:
		with console.status("[bold green]Checking token..."):
			check = utils.checktoken(service, token)
			if not check:
				console.print("Saved token expired, refreshing...", style="yellow")
				refresh = utils.refreshtoken(service, token)
				token = refresh if refresh else ""

	if not token:
		answer = Confirm.ask(f"Do you have a token for [b]{servicename}[/b]?", default=False)

		if answer:
			token = Prompt.ask("Paste here your token")
		else:
			username = Prompt.ask(f"[b]{servicename}[/b] username")
			password = Prompt.ask(f"[b]{servicename}[/b] password", password=True)
			with console.status(f"[bold green]Logging in to {servicename}..."):
				token = utils.login(service, username, password)
			if token:
				console.print(f"Logged in to [b]{servicename}[/b]!", style="green")
			else:
				console.print(f"Error: Unable to authenticate to [b]{servicename}[/b]", style="red")
				return

		with console.status("[bold green]Checking token..."):
			check = utils.checktoken(service, token)
		if not check:
			console.print(f"[b]{servicename}[/b] log in generated an invalid token! Report this issue!", style="red")
			return
		utils.addtoken(userid, service, token)

	with console.status("[bold green]Fetching library..."):
		books = utils.library(service, token)

	if not books:
		console.print("No books!", style="bold red")
		return

	table = Table(title=f"Available books for {servicename}", box=box.SIMPLE_HEAVY, title_justify="left")
	table.add_column("Id", style="cyan", justify="right")
	table.add_column("Internal id", style="magenta")
	table.add_column("Title", style="green")

	id2bookid = []
	downloadcovers = config.getboolean(service, "Cover", fallback=False)
	with console.status("[bold green]Preparing library..."):
		for (i, (bid, book)) in enumerate(books.items()):
			if downloadcovers:
				utils.cover(service, token, bid, book)
			table.add_row(str(i), bid, book['title'])
			id2bookid.append(bid)

	console.clear()
	console.print(table)
	console.print(f"Files are saved in [bold]{Path('files') / service}[/bold]")

	choices = parsebooks(Prompt.ask(bookprompt, default="none"), len(id2bookid))
	while choices is None:
		console.print("Invalid selection.", style="red")
		choices = parsebooks(Prompt.ask(bookprompt, default="none"), len(id2bookid))
	if not choices:
		console.print("Nothing selected.", style="yellow")
		return

	downloaded, failed = [], []
	for i in choices:
		bookid = id2bookid[int(i)]
		title = books[bookid]["title"]
		with Progress(
			TextColumn("[progress.description]{task.description}"),
			BarColumn(bar_width=None),
			TaskProgressColumn(),
			TimeElapsedColumn(),
			console=console,
			transient=True,
		) as progress:
			maintask = progress.add_task(f"Preparing {title}", total=100)

			def progressfun(update, status=""):
				progress.update(maintask, completed=update, description=status or f"Downloading {title}")

			try:
				pdfpath = utils.downloadbook(service, token, bookid, books[bookid], progressfun)
			except Exception as e:
				progress.update(maintask, completed=100, description=f"Failed: {title}")
				failed.append((title, str(e)))
				continue
			progress.update(maintask, completed=100, description=f"Done: {title}")

		downloaded.append((title, str(pdfpath)))

	lines = []
	if downloaded:
		lines.append("[bold green]Downloaded[/bold green]")
		lines.extend(f"  [green]✓[/green] {title} → [cyan]{path}[/cyan]" for title, path in downloaded)
	if failed:
		lines.append("[bold red]Failed[/bold red]")
		lines.extend(f"  [red]✗[/red] {title}: {error}" for title, error in failed)
	console.print(Panel("\n".join(lines), title="Summary", border_style="green" if not failed else "yellow", title_align="left"))

def parsebooks(answer, count):
	'''Parse a book selection, returning a list of indexes, [] for cancel and None for invalid input'''
	answer = answer.strip().lower()
	if answer in ["", "none"]:
		return []
	if answer in ["a", "all"]:
		return [str(i) for i in range(count)]

	selected = []
	for part in answer.split(","):
		part = part.strip()
		if re.fullmatch(r"[0-9]+", part):
			numbers = [int(part)]
		elif m := re.fullmatch(r"([0-9]+)\s*-\s*([0-9]+)", part):
			start, end = int(m.group(1)), int(m.group(2))
			if start > end:
				start, end = end, start
			numbers = range(start, end + 1)
		else:
			return None
		for number in numbers:
			if number >= count:
				return None
			if str(number) not in selected:
				selected.append(str(number))
	return selected

def downloadoneshot():
	if not utils.oneshots:
		console.print("No one-shot services are available.", style="yellow")
		return
	if config.getboolean("pdfgrabber", "OneshotWarning", fallback=True):
		answer = Confirm.ask("[bold red]Oneshot services are unstable and lead to lower-quality books than normal services (they often have only pictures/unselectable text). Do you wish to continue?[/bold red]", default=False)
		if not answer:
			return
	service = selectservice(utils.oneshots)
	servicename = utils.oneshots[service]
	urlmatch = utils.geturlmatch(service)

	url = ""
	first = True
	while not re.fullmatch(urlmatch, url):
		if not first:
			console.print(f"Invalid url for {servicename}!", style="red")
		first = False
		url = Prompt.ask(f"[b]{servicename}[/b] url")

	with Progress(
		TextColumn("[progress.description]{task.description}"),
		BarColumn(bar_width=None),
		TaskProgressColumn(),
		TimeElapsedColumn(),
		console=console,
		transient=True,
	) as progress:
		maintask = progress.add_task("Starting...", total=100)

		def progressfun(update, status=""):
			progress.update(maintask, completed=update, description=status or "Downloading")

		pdfpath = utils.downloadoneshot(service, url, progressfun)
		progress.update(maintask, completed=100, description="Done")

	console.print(f"[bold green]Done![/bold green] Your book is in {pdfpath}")

def register():
	users = utils.getusers()
	username = Prompt.ask("Username")
	while username in users:
		console.print("That username already exists!", style="red")
		username = Prompt.ask("Username")
	password = Prompt.ask("Password", password=True)
	repeatpassword = Prompt.ask("Retype password", password=True)
	if (password != repeatpassword):
		console.print("Passwords do not match!", style="bold red")
		return None
	utils.register(username, password)
	console.print(f"Signed up {username}, now you can download books!", style="bold green")
	return username

def logout():
	global userid
	userid = False
	console.print("Logged out!", style="bold magenta")

def books():
	available = utils.listbooks()
	if not available:
		console.print("No books downloaded yet.", style="yellow")
		return

	table = Table(title="Downloaded books", box=box.SIMPLE_HEAVY, title_justify="left")
	table.add_column("Service", style="cyan")
	table.add_column("Title", style="green")
	table.add_column("Pages", style="magenta", justify="right")
	table.add_column("Path", style="blue")

	for i in available:
		table.add_row(i["service"], i["title"], str(i["pages"]), i["path"])

	console.print(table)

def menu():
	table = Table(box=box.ROUNDED, show_header=False, title="[bold]What do you want to do?[/bold]", title_justify="left")
	table.add_column("Key", style="bold cyan", justify="center", width=3)
	table.add_column("Action", style="white")
	options = [
		("d", "Download books from your libraries"),
		("v", "View downloaded books"),
		("t", "Manage saved tokens"),
		("r", "Register a new scuolagrab user"),
		("l", "Log out"),
		("q", "Quit"),
	]
	if utils.oneshots:
		options.insert(1, ("o", "Download from a one-shot link"))
	for key, label in options:
		table.add_row(key, label)
	console.print(table)
	return Prompt.ask("Your choice", choices=[key for key, _ in options], default="d", show_choices=False)

def main():
	if sys.version_info < (3, 10):
		console.print("Python version 3.10 or greater is required!", style="bold red")
		exit()
	showbanner = config.getboolean("pdfgrabber", "ShowBanner", fallback=True)
	if showbanner:
		console.print(center(banner), style="green bold", no_wrap=True, highlight=False)
		console.print(Rule("version 1.0 — by vincyxiroff"))
	else:
		console.print(Rule("scuolagrab version 1.0"))

	while True:
		action = menu()
		match action:
			case "r":
				register()
			case "d":
				downloadbook()
			case "o":
				downloadoneshot()
			case "l":
				logout()
			case "t":
				managetokens()
			case "v":
				books()
			case "q":
				console.print("Bye!", style="bold green")
				exit()
			case _:
				console.print("Invalid action!", style="bold red")
		console.print(Rule())

if __name__ == '__main__':
	try:
		main()
	except KeyboardInterrupt:
		console.print("\nBye!", style="bold green")
		try:
			sys.exit(0)
		except SystemExit:
			os._exit(0)
