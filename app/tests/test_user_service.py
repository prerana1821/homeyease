# app/tests/test_user_service.py
import pytest
from app.services.user_service import UserService


# A very small in-memory FakeDB used for unit tests.
class FakeTable:

    def __init__(self, db, name):
        self.db = db
        self.name = name
        self._where = {}

    def select(self, *args, **kwargs):
        # ignore columns selection
        return self

    def eq(self, col, val):
        self._where[col] = val
        return self

    def limit(self, n):
        self._limit = n
        return self

    def insert(self, payload):
        self._operation = ("insert", payload)
        return self

    def update(self, payload):
        self._operation = ("update", payload)
        return self

    def upsert(self, payload, on_conflict=None):
        # use update/insert logic in execute
        self._operation = ("upsert", payload, on_conflict)
        return self

    def delete(self):
        self._operation = ("delete", None)
        return self

    def execute(self):
        op = getattr(self, "_operation", None)
        if not op:
            # select
            rows = []
            for r in self.db.tables.get(self.name, []):
                match = True
                for k, v in getattr(self, "_where", {}).items():
                    if str(r.get(k)) != str(v):
                        match = False
                        break
                if match:
                    rows.append(r)
            return {"data": rows}
        typ = op[0]
        if typ == "insert":
            payload = op[1]
            payload = dict(payload)
            # auto id
            payload["id"] = self.db.next_id(self.name)
            self.db.tables.setdefault(self.name, []).append(payload)
            return {"data": [payload]}
        if typ == "update":
            payload = op[1]
            updated = []
            for r in self.db.tables.get(self.name, []):
                match = True
                for k, v in getattr(self, "_where", {}).items():
                    if str(r.get(k)) != str(v):
                        match = False
                        break
                if match:
                    r.update(payload)
                    updated.append(r)
            return {"data": updated}
        if typ == "upsert":
            payload = op[1]
            on_conflict = op[2]
            key = on_conflict
            # find
            found = None
            for r in self.db.tables.get(self.name, []):
                if key and key in payload and str(r.get(key)) == str(payload.get(key)):
                    found = r
                    break
            if found:
                found.update(payload)
                return {"data": [found]}
            else:
                payload["id"] = self.db.next_id(self.name)
                self.db.tables.setdefault(self.name, []).append(dict(payload))
                return {"data": [payload]}
        if typ == "delete":
            new_rows = []
            deleted = []
            for r in self.db.tables.get(self.name, []):
                match = True
                for k, v in getattr(self, "_where", {}).items():
                    if str(r.get(k)) != str(v):
                        match = False
                        break
                if match:
                    deleted.append(r)
                else:
                    new_rows.append(r)
            self.db.tables[self.name] = new_rows
            return {"data": deleted}


class FakeDB:

    def __init__(self):
        self.tables = {}
        self.counters = {}

    def table(self, name):
        return FakeTable(self, name)

    def next_id(self, name):
        self.counters.setdefault(name, 0)
        self.counters[name] += 1
        return self.counters[name]


@pytest.fixture
def db():
    return FakeDB()


@pytest.fixture
def user_service(db):
    return UserService(db)


def test_create_and_get_user(user_service):
    res = user_service.create_or_update_user(whatsapp_id="wa_1", name="Alice")
    assert res["ok"]
    data = res["data"]
    assert data and data["whatsapp_id"] == "wa_1"
    # get_by_whatsapp
    got = user_service.get_user(whatsapp_id="wa_1")
    assert got["ok"]
    assert got["data"]["name"] == "Alice"


def test_update_user(user_service):
    _ = user_service.create_or_update_user(whatsapp_id="wa_2", name="Bob")
    upd = user_service.create_or_update_user(whatsapp_id="wa_2", diet="vegan")
    assert upd["ok"]
    got = user_service.get_user(whatsapp_id="wa_2")
    assert got["ok"]
    assert got["data"]["diet"] == "vegan"


def test_delete_user(user_service):
    _ = user_service.create_or_update_user(whatsapp_id="wa_del", name="ToDelete")
    del_res = user_service.delete_user(whatsapp_id="wa_del")
    assert del_res["ok"]
    # ensure gone
    got = user_service.get_user(whatsapp_id="wa_del")
    assert got["ok"] and got["data"] is None
