# _bootstrap（仅沙箱开发环境需要）

本目录仅用于 DSH 沙箱内安装 Python 依赖：沙箱会模拟 POSIX 权限位，
而 `pip`/`ensurepip`/`pytest` 用 `tempfile` 创建的临时目录是 0700 权限，
会被沙箱拒绝访问。`sitecustomize.py` 通过 `PYTHONPATH` 注入，把所有
`os.mkdir`/`os.open` 的 mode 强制为宽松值。

普通机器上**不需要**它，直接 `pip install -r requirements.txt` 即可。
在沙箱内使用时：

```powershell
$env:PYTHONPATH = "$(Get-Location)\_bootstrap"
& .\.venv\Scripts\python.exe -m pip install -r requirements.txt
```
