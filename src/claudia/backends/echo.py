from time import sleep


def run(model, ui):
    ui.loading("Waiting...")
    sleep(1)
    ui.loading("still waiting...")
    sleep(1)
    ui.hello()
    while True:
        query = ui.prompt()
        if query is None:
            break
        ui.loading("calculating...")
        sleep(1)
        ui.answer("echo: " + query)
    ui.bye()
