"""Testes da API do sandbox. Correr a partir de modules/gm-panel:
    python -m unittest backend.test_api
"""
import os
import tempfile
import unittest

os.environ.setdefault("PRAGA_DATA", tempfile.mkdtemp(prefix="praga-sandbox-"))

from fastapi.testclient import TestClient  # noqa: E402

from backend.app import app  # noqa: E402


class SandboxApiTests(unittest.TestCase):
    def setUp(self):
        self.c = TestClient(app)
        self.assertEqual(self.c.post("/api/reset", json={"seed": "t"}).status_code, 200)

    def test_initial_state(self):
        s = self.c.get("/api/state").json()
        self.assertEqual(s["turn"], 1)
        self.assertFalse(s["plague_active"])
        self.assertEqual(len(s["suggested_foci"]), 6)
        self.assertEqual(len(s["owner"]), len(s["plague"]))
        self.assertEqual(s["pending"], [])

    def test_orders_queue_and_replace(self):
        self.c.post("/api/gm/orders", json={"type": "plague_state", "value": "active"})
        r = self.c.post("/api/gm/orders", json={"type": "plague_state", "value": "dormant"}).json()
        self.assertEqual(r["pending"], [{"type": "plague_state", "value": "dormant"}])
        r = self.c.delete("/api/gm/orders/0").json()
        self.assertEqual(r["pending"], [])

    def test_invalid_order_is_400_with_message(self):
        r = self.c.post("/api/gm/orders", json={"type": "plague_intensity", "value": "extreme"})
        self.assertEqual(r.status_code, 400)
        self.assertIn("intensidade", r.json()["detail"])

    def test_preview_matches_resolution(self):
        foci = self.c.get("/api/state").json()["suggested_foci"]
        self.c.post("/api/gm/orders", json={"type": "plague_state", "value": "active"})
        self.c.post("/api/gm/orders", json={"type": "plague_focus", "region": foci[0]})
        prev = self.c.post("/api/preview", json={"turns": 1}).json()
        after = self.c.post("/api/turn").json()
        self.assertEqual(prev["owner"], after["owner"])
        self.assertEqual(prev["plague"], after["plague"])
        self.assertTrue(after["plague_active"])
        self.assertEqual(after["pending"], [])
        self.assertTrue(any(c["kind"] == "gm" for c in after["chronicle"]))

    def test_preview_does_not_change_state(self):
        before = self.c.get("/api/state").json()
        self.c.post("/api/preview", json={"turns": 5})
        self.assertEqual(self.c.get("/api/state").json()["turn"], before["turn"])

    def test_region_detail(self):
        foci = self.c.get("/api/state").json()["suggested_foci"]
        r = self.c.get(f"/api/region/{foci[0]}").json()
        self.assertTrue(r["suggested_focus"])
        self.assertEqual(self.c.get("/api/region/999999").status_code, 404)


    def test_player_view_hides_unknown(self):
        state = self.c.get("/api/state").json()
        fid = next(f["id"] for f in state["factions"] if f["active"])
        v = self.c.get(f"/api/view/{fid}").json()
        self.assertEqual(len(v["owner"]), len(state["owner"]))
        unknown = [rid for rid in range(1, len(v["fog"])) if v["fog"][rid] == 0]
        self.assertTrue(unknown, "no início quase tudo é desconhecido")
        self.assertTrue(all(v["owner"][r] == 0 and v["plague"][r] == 0 for r in unknown))
        self.assertTrue(set(map(int, v["regions"])) == {r for r in range(1, len(v["fog"])) if v["fog"][r] > 0})
        self.assertEqual(self.c.get("/api/view/99999").status_code, 404)

    def test_gm_rumour_reaches_player(self):
        state = self.c.get("/api/state").json()
        fid = next(f["id"] for f in state["factions"] if f["active"])
        r = self.c.post("/api/gm/orders", json={"type": "rumor", "text": "Viu-se fumo no horizonte.", "factions": [fid]})
        self.assertEqual(r.status_code, 200)
        self.assertEqual(self.c.post("/api/gm/orders", json={"type": "rumor", "text": ""}).status_code, 400)
        self.c.post("/api/turn")
        inbox = self.c.get(f"/api/view/{fid}").json()["inbox"]
        self.assertIn("Viu-se fumo no horizonte.", [m["text"] for m in inbox if m["kind"] == "gm"])


if __name__ == "__main__":
    unittest.main()
