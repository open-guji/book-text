# vol02 交 Gemini（overview#401）

- `in/part01.txt` … `part07.txt`：一行一段，行首 `[P001]` 是 reflow 自然段号；繁体无标点，夹注 `<…>`，阙文 `□`，页码标记已去。每份约 5,000 字。
- 用法：把 #401 里的提示词贴在文件内容前面，交给 Gemini；输出存成 `out/partNN.txt`，格式同输入（一行一段、段号原样）。
- 收回：open-guji-cv `scripts/siku_volume_extract.py gemini-import --vol 2 --lines-md ../../002.lines.md --in-dir out --parts 1 --book-index <book-index> --out result`。
- 段号随 `002.lines.md` 与 reflow 而定：底本改了要重新导出，旧的输出不能再用。
