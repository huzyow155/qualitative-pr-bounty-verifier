import os
import tempfile
import pytest
from gltest.direct import loader, wasi_mock
from gltest.direct.loader import create_address

# 1. Windows temporary file unlink fix:
# On Windows, os.unlink raises PermissionError if fd 0 (stdin) was duplicated to it.
def _windows_safe_inject(vm):
    try:
        from genlayer.py import calldata
        from genlayer.py.types import Address
        if not getattr(Address, "_bytes_eq_patched", False):
            orig_eq = Address.__eq__
            def _addr_eq(self, other):
                if isinstance(other, (bytes, bytearray)):
                    return self.as_bytes == other
                return orig_eq(self, other)
            Address.__eq__ = _addr_eq
            Address._bytes_eq_patched = True
    except ImportError:
        return

    sender_addr = vm.sender
    if isinstance(sender_addr, bytes):
        sender_addr = Address(sender_addr)

    contract_addr = vm._contract_address
    if isinstance(contract_addr, bytes):
        contract_addr = Address(contract_addr)

    origin_addr = vm.origin
    if isinstance(origin_addr, bytes):
        origin_addr = Address(origin_addr)

    message_data = {
        'contract_address': contract_addr,
        'sender_address': sender_addr,
        'origin_address': origin_addr,
        'stack': [],
        'value': vm._value,
        'datetime': vm._datetime,
        'is_init': False,
        'chain_id': vm._chain_id,
        'entry_kind': 0,
        'entry_data': b'',
        'entry_stage_data': None,
    }

    encoded = calldata.encode(message_data)

    fd, path = tempfile.mkstemp()
    try:
        os.write(fd, encoded)
        os.lseek(fd, 0, os.SEEK_SET)

        original_stdin = os.dup(0)
        vm._original_stdin_fd = original_stdin

        os.dup2(fd, 0)
    finally:
        os.close(fd)
        try:
            os.unlink(path)
        except OSError:
            pass

loader._inject_message_to_fd0 = _windows_safe_inject


# 2. Preserve raw mock string format for LLM responses:
# Real GenVM nodes return raw JSON strings from the LLM. In direct mode,
# wasi_mock auto-deserialized JSON strings into dicts, breaking contracts
# that parse raw JSON strings via json.loads().
_orig_handle_llm = wasi_mock._handle_llm_request
def _preserve_raw_string_handle_llm(vm, data):
    prompt = data.get("prompt", "")
    resp = vm._match_llm_mock(prompt)
    if resp is not None:
        return {"ok": resp}
    return _orig_handle_llm(vm, data)

wasi_mock._handle_llm_request = _preserve_raw_string_handle_llm


# 3. Direct mode mock for gl.block:
# Real GenVM nodes provide gl.block (e.g., gl.block.number, gl.block.timestamp).
# In direct mode, we supply a mock block object so contracts can read the live block.
from types import SimpleNamespace


def _ensure_gl_block():
    try:
        import genlayer.gl as gl
        gl.block = SimpleNamespace(number=1, timestamp=1700000000)
    except Exception:
        pass


_orig_load_contract_class = loader.load_contract_class
def _patched_load_contract_class(*args, **kwargs):
    cls = _orig_load_contract_class(*args, **kwargs)
    _ensure_gl_block()
    return cls

loader.load_contract_class = _patched_load_contract_class


@pytest.fixture(autouse=True)
def auto_set_sender(direct_vm):
    """Ensure direct_vm sender is always propagated to gl.message."""
    _ensure_gl_block()
    direct_vm.sender = create_address("alice")


