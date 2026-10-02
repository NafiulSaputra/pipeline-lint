"""A file that defines its own DAG helper; it does not import Airflow."""


class DAG:
    def __init__(self, name: str) -> None:
        self.name = name


graph = DAG("dependency-graph")
