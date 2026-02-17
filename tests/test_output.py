"""Tests for atlassian_cli.output."""

import json

from atlassian_cli.output import emit, emit_error, emit_json, set_json_mode


class TestEmit:
    def test_text_mode(self, capsys):
        set_json_mode(False)
        emit("OK", "Done")
        assert capsys.readouterr().out.strip() == "OK Done"

    def test_json_mode(self, capsys):
        set_json_mode(True)
        emit("OK", "Done", data={"key": "PROJ-1"})
        output = json.loads(capsys.readouterr().out)
        assert output["status"] == "ok"
        assert output["message"] == "Done"
        assert output["key"] == "PROJ-1"
        set_json_mode(False)

    def test_json_mode_no_data(self, capsys):
        set_json_mode(True)
        emit("OK", "Done")
        output = json.loads(capsys.readouterr().out)
        assert output == {"status": "ok", "message": "Done"}
        set_json_mode(False)


class TestEmitJson:
    def test_outputs_json(self, capsys):
        emit_json({"foo": "bar"})
        output = json.loads(capsys.readouterr().out)
        assert output == {"foo": "bar"}


class TestEmitError:
    def test_text_mode(self, capsys):
        set_json_mode(False)
        emit_error("broken")
        assert "ERR broken" in capsys.readouterr().err

    def test_json_mode(self, capsys):
        set_json_mode(True)
        emit_error("broken")
        output = json.loads(capsys.readouterr().err)
        assert output["status"] == "error"
        assert output["message"] == "broken"
        set_json_mode(False)
