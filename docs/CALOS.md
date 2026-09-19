# OpenAurum no calOS

O OpenAurum nasceu dentro do **calOS**, os dotfiles Arch + Hyprland do autor. Esta página mostra como os dois se encaixam; serve também de exemplo para integrar o OpenAurum a qualquer outro desktop.

## Detecção

`openaurum/integrations.py` considera que está num calOS quando existe `~/.config/calos/current/theme`. Nesse caso:

| O quê | De onde vem |
|---|---|
| Paleta das cenas "Do tema" | `@accent` do `waybar.css` do tema + cores normais do `alacritty.toml` |
| `openaurum-cli theme` | `keyboard.conf` do tema (`mode`, `brightness`, `speed`, `color`), senão a cor de destaque bem viva |
| Cena "Wallpaper" | fundo do monitor sob o mouse (`calos-cursor-output` + `~/.local/state/calos/background/`) |
| Modo de tela | `openaurum-cli screen` (e, como reserva, `$XDG_RUNTIME_DIR/calos-screen-mode`) |

O que estiver no `~/.config/openaurum/config.conf` tem prioridade sobre o calOS.

## Ganchos

Os scripts do calOS chamam o CLI em segundo plano (`&>/dev/null &`), por caminho absoluto, porque o `PATH` do Hyprland não inclui `~/.local/bin`:

| Script do calOS | Chamada |
|---|---|
| `calos-theme-set` | `~/.local/bin/openaurum-cli theme` |
| `calos-theme-bg` (SUPER+CTRL+B) | `~/.local/bin/openaurum-cli event wallpaper` |
| `calos-toggle-gamemode` (CTRL+SUPER+G) | `~/.local/bin/openaurum-cli overlay game on\|off --auto` |
| `calos-toggle-layout` (SUPER+SHIFT+SPACE) | `~/.local/bin/openaurum-cli overlay colemak on\|off --auto` |
| `calos-screen-mode` (Night / Cave) | `~/.local/bin/openaurum-cli screen <modo>` |
| `calos-menu` → Style → Keyboard RGB | `~/.local/bin/openaurum` |

E a regra de janela no Hyprland (`windowrules.lua`), para o app abrir flutuando:

```lua
hl.window_rule({
	match = { class = "^(io.github.its_danilo.OpenAurum)$" },
	center = true,
	float = true,
	size = "560 840",
})
```

## Cave Mode

Em `cave`, o teclado vai para o efeito Static em vermelho bem escuro (`#100000`), em qualquer tema, e o efeito anterior é guardado. Ao sair do Cave, tudo volta exatamente como estava. A tabela de cores por tecla não é tocada: são só uma ou duas gravações de efeito.
