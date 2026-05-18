from time import sleep

from ..ui import UI


def main():
    with UI.from_env() as ui:
        sleep(1)
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
