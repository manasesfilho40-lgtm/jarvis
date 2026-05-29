import sys, os, json, pytest, tempfile
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from actions.negotiation_script import load_script, negotiation_script_action


TEST_SCRIPT = {
    "opening_message": "Teste de abertura",
    "objection_handling": {"nao_temos_interesse": "Teste objecao"},
    "counter_proposal": "Teste contraproposta",
    "closing_message": "Teste fechamento",
    "follow_up": "Teste follow-up",
    "urgency_triggers": {"scarcity": "Teste escassez", "social_proof": "Teste prova social"},
    "metadata": {"product": "Teste", "price": "R$ 100", "max_discount": "10%"}
}


@pytest.fixture(autouse=True)
def isolate_scripts():
    with tempfile.TemporaryDirectory() as tmp:
        scripts_dir = Path(tmp)
        with patch("actions.negotiation_script.SCRIPTS_DIR", scripts_dir):
            yield scripts_dir


class TestLoadScript:
    def test_load_nonexistent(self, isolate_scripts):
        assert load_script("produto_inexistente") is None

    def test_load_existing(self, isolate_scripts):
        script_path = isolate_scripts / "produto_teste_script.json"
        script_path.write_text(json.dumps(TEST_SCRIPT, indent=2), encoding="utf-8")
        script = load_script("produto teste")
        assert script is not None
        assert script["opening_message"] == "Teste de abertura"
        assert "urgency_triggers" in script

    def test_load_normalizes_name(self, isolate_scripts):
        script_path = isolate_scripts / "layout_de_ad_para_loja_script.json"
        script_path.write_text(json.dumps(TEST_SCRIPT, indent=2), encoding="utf-8")
        script = load_script("Layout de Ad para Loja")
        assert script is not None


class TestNegotiationScriptAction:
    def test_load_action_nonexistent(self, isolate_scripts):
        result = negotiation_script_action({"action": "load", "product": "inexistente"})
        assert "No script found" in result

    def test_load_action_existing(self, isolate_scripts):
        script_path = isolate_scripts / "produto_teste_script.json"
        script_path.write_text(json.dumps(TEST_SCRIPT, indent=2), encoding="utf-8")
        result = negotiation_script_action({"action": "load", "product": "produto teste"})
        assert "Teste de abertura" in result

    def test_generate_missing_params(self, isolate_scripts):
        result = negotiation_script_action({"action": "generate"})
        assert "Error" in result

    def test_generate_missing_price(self, isolate_scripts):
        result = negotiation_script_action({"action": "generate", "product": "Teste"})
        assert "Error" in result

    def test_unknown_action(self, isolate_scripts):
        result = negotiation_script_action({"action": "invalid"})
        assert "Unknown" in result

    @patch("actions.negotiation_script.generate_negotiation_script")
    def test_generate_calls_gemini(self, mock_generate, isolate_scripts):
        mock_generate.return_value = "Script generated"
        result = negotiation_script_action({
            "action": "generate", "product": "Teste", "price": "R$ 100"
        })
        mock_generate.assert_called_once_with("Teste", "R$ 100", "0%", "professional")
