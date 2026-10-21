# 1.11.1

Ref2VA and MiniMax H3 on Windows now read disk-backed tensor slices synchronously through a bounded 1 MiB pageable buffer. This avoids the native overlapped file-to-CUDA reads that failed with error 1450 (`hostbuf_file_reader_read failed`), while retaining the dynamic VRAM loader and quantized model metadata. Both PyTorch and SageAttention use the repair. Other model loaders are unchanged.

Incomplete files and read failures still stop the affected job with an error; failed jobs are never silently retried. Models, Library media and settings are preserved. Loading may be slower than native asynchronous transfers.
