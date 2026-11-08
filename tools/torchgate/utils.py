import torch


def linspace(start, stop, num, endpoint=True):
    """Return a 1D tensor of evenly spaced values.

    This mirrors the NumPy-style `endpoint` argument used by the original TorchGate
    implementation, while remaining compatible with PyTorch tensors.
    """
    if num <= 0:
        return torch.empty(0, dtype=torch.float32)

    start = torch.as_tensor(start)
    stop = torch.as_tensor(stop)

    if endpoint and num == 1:
        return start.clone().reshape(1)

    if endpoint:
        step = (stop - start) / (num - 1)
        values = start + step * torch.arange(num, dtype=torch.result_type(start, stop, torch.float32))
    else:
        step = (stop - start) / num
        values = start + step * torch.arange(num, dtype=torch.result_type(start, stop, torch.float32))

    return values


def temperature_sigmoid(x, threshold=1.0, temperature=1.0):
    """A temperature-scaled sigmoid used for spectral gating thresholds."""
    if temperature == 0:
        return (x > threshold).to(x.dtype)
    return torch.sigmoid((x - threshold) / temperature)


def amp_to_db(x, ref=1.0, amin=1e-10, top_db=80.0):
    """Approximate the common amplitude-to-decibel conversion used in audio processing."""
    x = torch.abs(x)
    x = x.clamp_min(amin)
    db = 20.0 * torch.log10(x / ref)
    if top_db is not None:
        db = torch.clamp(db, min=db.max() - top_db, max=db.max())
    return db
