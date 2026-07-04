FROM python:3.11-slim

RUN useradd -m -u 1000 sandboxer && mkdir /work && chown sandboxer /work

# Install common packages students might use.
# pip is available during build; the sandbox itself has no network at runtime.
RUN pip install --no-cache-dir numpy

USER sandboxer
WORKDIR /work

CMD ["python", "-c", "print('sandbox ready')"]
