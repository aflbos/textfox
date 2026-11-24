
```
   __            __  ____          
  / /____  _  __/ /_/ __/___  _  __
 / __/ _ \| |/_/ __/ /_/ __ \| |/_/
/ /_/  __/>  </ /_/ __/ /_/ />  <  
\__/\___/_/|_|\__/_/  \____/_/|_|  
```

_a firefox theme for the tui enthusiast_

> [!NOTE]
> **Edição Waterfox** (branch `main` deste fork). Fork pessoal do textfox ajustado para o
> Waterfox e carregado como mod local do [Sine](https://github.com/CosmoCreeper/Sine).
>
> - `chrome/waterfox.css`: estilo textfox para a barra de status do Waterfox
>   (`#status-bar`), para as abas em árvore (seta e botão de nova aba) e para a
>   área "tools" da barra lateral (título no lugar com a barra retraída, ícones
>   distribuídos com ela expandida).
>   Variáveis novas em `defaults.css`: `--tf-statusbar-margin` e `--tf-statusbar-padding`.
> - `chrome/config.css`: configuração pessoal, versionada nesta edição. Inclui
>   contorno nas abas e as cores dos contornos vindas do tema ativo.
> - Cores com o [Adaptive Tab Bar Colour](https://addons.mozilla.org/firefox/addon/adaptive-tab-bar-colour/):
>   a extensão aplica um tema derivado de cada página, e `config.css` usa duas
>   cores desse tema. Ajuste-as no "Theme builder" da extensão:
>
>   | Cor no textfox | Theme builder | Cor do tema |
>   | --- | --- | --- |
>   | Contorno normal (`--tf-border`) | URL bar → Border | `toolbar_field_border` |
>   | Destaque ao passar o mouse, aba selecionada e títulos (`--tf-accent`) | Selected tab → Border | `tab_line` |
>
>   Cada valor é somado ao Background do mesmo cartão e clareia a cor da página
>   (escurece no modo claro). O fundo do textfox vem de Tab bar → Background, então
>   o contorno só aparece se o seu valor ficar acima desse. Para o destaque se
>   distinguir, use em Selected tab → Border um valor maior que o de
>   URL bar → Border.
>   Se o tema não definir `toolbar_field_border`, o contorno volta a usar
>   uma mistura da cor de fundo com a dos ícones. O destaque usa a cor dos
>   ícones quando o tema não fornece `tab_line`.
> - Feche o Waterfox antes de instalar, atualizar ou remover o mod. Com o Sine
>   já instalado, use o comando abaixo para instalar ou atualizar no perfil
>   padrão. Se houver mais de um perfil padrão, indique o caminho do perfil
>   com `-ProfilePath "C:\caminho\do\perfil"`.
>
>   ```powershell
>   powershell -ExecutionPolicy Bypass -File tools\install-sine.ps1
>   ```
>
>   O script valida o registro do Sine antes de trocar os arquivos. Ele instala
>   o mod em `chrome\sine-mods\textfox-waterfox`, desliga as atualizações
>   automáticas para essa cópia e desabilita o textfox original, se estiver ativo.
> - Para remover o mod local:
>
>   ```powershell
>   powershell -ExecutionPolicy Bypass -File tools\install-sine.ps1 -Uninstall
>   ```
>
>   A remoção afeta apenas o mod local. Para voltar ao textfox original,
>   reative-o no painel do Sine.
> - A pasta `chrome\textfox-sine-backups` guarda um diretório por operação, com
>   o registro anterior em `mods.json` e o pacote substituído em `previous/`,
>   quando ele existia. Se precisar recuperar uma versão, feche o Waterfox e
>   use esses arquivos para restaurar a pasta e a entrada do mod. Preserve
>   as alterações posteriores dos outros mods no registro.
> - Atualizações do textfox original: `git fetch upstream && git merge upstream/main`
>   na `main`. O remoto `upstream` aponta para
>   [adriankarlen/textfox](https://github.com/adriankarlen/textfox); `origin` é este fork.

## Preview

![image](https://github.com/adriankarlen/textfox/blob/main/misc/vertical-tabs.png)

![image](https://github.com/adriankarlen/textfox/blob/main/misc/horizontal-tabs.png)

> [!NOTE]
> The color scheme used in the pictures is [Rosé Pine Moon](https://github.com/rose-pine/firefox).
> `textfox` tries to not hard code any colors, [Firefox Color extension](https://addons.mozilla.org/en-US/firefox/addon/firefox-color/) is the
> recommended approach to coloring Firefox with `textfox`.

## Installation

> [!WARNING]
> textfox does not yet support Firefox's new "Nova" UI. Until it does, set
> `browser.nova.enabled` to `false` in `about:config` (the provided `user.js`
> and the Nix modules do this for you), then restart Firefox.

### Installation script

1. Download or clone the repo and close Firefox.
2. Run `bash tf-install.sh` and enter the profile path, or pass the path as
   an argument.

The script installs the theme in the profile's `chrome/textfox/` directory.
It creates `chrome/userChrome.css` and `chrome/userContent.css` as imports
of that package. It offers to add `user.js` if the profile has none.

If a first installation finds a stylesheet at either entry point, it stops.
This also covers older textfox installations that placed the full CSS in
`chrome/`. Review and save the existing entry points before migrating, or
use the manual instructions to combine styles. On subsequent updates, the
script keeps your `chrome/textfox/config.css` and archives the old package
under `chrome/textfox-backups/`.

### Manual

1. Download the files
2. Go to `about:profiles`
3. Find the names of target profiles (ex: `Profile: Default`)
4. Open the profile's root directory
5. Copy the repository's `chrome` directory to `<profile>/chrome/textfox`.
   At the beginning of `<profile>/chrome/userChrome.css` and
   `<profile>/chrome/userContent.css`, add
   `@import url("textfox/userChrome.css");` and
   `@import url("textfox/userContent.css");` respectively. Keep any existing
   `@charset` rule first. Create the entry files if they are missing.
6. Apply the preferences from `user.js`. If the profile already has a
   `user.js`, add the desired preferences to it.
7. Restart Firefox.

> [!IMPORTANT]
> textfox now supports horizontal tabs, to enable them change the
> `--tf-display-horizontal-tabs` variable in your `config.css` to `block`. See
> [CSS configurations](#css-configurations) for more info.

> [!NOTE]
> If you don't want to use the provided user.js, please read through it and
> apply the settings in `about:config` manually. These are needed for the css to
> work.

### Nix

This repo includes Home Manager and NixOS modules. Home Manager links the
stylesheets and generates `config.css` from `textfox.config`.

The NixOS wrapper installs two generated entry files in the Firefox profile.
It updates its own unedited files and keeps other files in `chrome/`. If it
encounters existing or edited entry files, it skips the update and logs the
conflict in the Browser Console. To migrate a legacy profile, close Firefox,
review and save the two existing entry files, then move them aside and launch
the wrapper. Put additional rules in `textfox.extraUserChrome` and
`textfox.extraUserContent`.

On Linux, `nix flake check --no-update-lock-file` builds the wrapped Firefox
with the NixOS module enabled in a test configuration. Use `nix build .#default`
to build the standalone stylesheet package. Textfox pins Nixpkgs 26.05 for
the wrapper and preserves the existing Linux and macOS package targets.
To call the wrapper directly from another flake on
x86-64 Linux, use `textfox.lib.wrapTextfox.x86_64-linux pkgs.firefox-unwrapped { }`.

To enable the module, add the repo as a flake input, import the module, and enable textfox.

<details><summary>Install using your home-manager module defined within your `nixosConfigurations`:</summary>

```nix

  # flake.nix

  {

      inputs = {
         # ---Snip---
         home-manager = {
           url = "github:nix-community/home-manager";
           inputs.nixpkgs.follows = "nixpkgs";
         };

         textfox.url = "github:adriankarlen/textfox";
         # ---Snip---
      }

      outputs = {nixpkgs, home-manager, ...} @ inputs: {
          nixosConfigurations.HOSTNAME = nixpkgs.lib.nixosSystem {
            specialArgs = { inherit inputs; };
            modules = [
            home-manager.nixosModules.home-manager
              {
               # Must pass in inputs so we can access the module
                home-manager.extraSpecialArgs = {
                  inherit inputs;
                };
              }
           ];
        };
     }
  }
```
```nix

# home.nix

imports = [ inputs.textfox.homeManagerModules.default ];

textfox = {
    enable = true;
    # Replace with the names of profiles, defined in home-manager, or find existing ones in `about:profiles`
    profiles = ["profile_1" "profile_2"];
    config = {
        # Optional config
    };
};
```
</details>

<details><summary>Install using `home-manager.lib.homeManagerConfiguration`:</summary>

```nix

  # flake.nix

  {
    inputs = {
       # ---Snip---
       home-manager = {
         url = "github:nix-community/home-manager";
         inputs.nixpkgs.follows = "nixpkgs";
       };

       textfox.url = "github:adriankarlen/textfox";
       # ---Snip---
    }

    outputs = {nixpkgs, home-manager, textfox ...}: {
        homeConfigurations."user@hostname" = home-manager.lib.homeManagerConfiguration {
            pkgs = nixpkgs.legacyPackages.x86_64-linux;

            modules = [
                textfox.homeManagerModules.default
                # ...
            ];
        };
    };
  }
```
  ```nix

  # home.nix

  textfox = {
      enable = true;
      # Replace with the names of profiles, defined in home-manager, or find existing ones in `about:profiles`
      profiles = ["profile_1" "profile_2"];
      config = {
          # Optional config
      };
  };
  ```
</details>

<details><summary>Configuration options:</summary>

All configuration options are optional and can be set as this example shows (real default values [can be found below](#defaults)):

```nix

  textfox = {
      enable = true;
      # Replace with the names of profiles, defined in home-manager, or find existing ones in `about:profiles`
      profiles = ["profile_1" "profile_2"];
      config = {
        background = {
          color = "#123456";
        };
        border = {
          color = "#654321";
          width = "4px";
          transition = "1.0s ease";
          radius = "3px";
        };
        displayWindowControls = true;
        displayNavButtons = true;
        displayUrlbarIcons = true;
        displaySidebarTools = false;
        displayTitles = false;
        newtabLogo = "   __            __  ____          \A   / /____  _  __/ /_/ __/___  _  __\A  / __/ _ \\| |/_/ __/ /_/ __ \\| |/_/\A / /_/  __/>  </ /_/ __/ /_/ />  <  \A \\__/\\___/_/|_|\\__/_/  \\____/_/|_|  ";
        font = {
          family = "Fira Code";
          size = "15px";
          accent = "#654321";
        };
        tabs = {
          horizontal.enable = true;
          vertical.enable = true;
        };
        navbar = {
          margin = "8px 8px 2px";
          padding = "4px";
        };
        bookmarks = {
          alignment = "left";
        };
        icons = {
          toolbar.extensions.enable = true;
          context.extensions.enable = true;
          context.firefox.enable = true;
        };
        textTransform = "uppercase";
        extraConfig = "/* custom css here */";
      };
  };
```
</details>

## Uninstallation

For a Sine installation, use `tools\install-sine.ps1 -Uninstall` as described
in the Waterfox section above.

### Uninstall script

Close Firefox and run `bash tf-uninstall.sh`. The script archives the managed
package and its untouched entry files in `chrome/textfox-backups/`. It also
archives `user.js` if the installer created it and its contents are unchanged.
If you edited an entry file, remove any remaining textfox import from it
manually. For a legacy layout without a managed package, follow the manual
instructions below.

### Manual

1. Use `about:profiles` to locate the profile, then close Firefox.
2. Remove the textfox imports from the entry files. Move the textfox package
   out of `chrome/`, keeping files that belong to other customizations.
3. For older layouts, identify the textfox files before moving them. Compare
   any previous `chrome-YYYYMMDD_HHMMSS.bak` backup with the active profile
   and restore only the files you need.
4. Revert the textfox preferences you added, as needed. Restart Firefox.

## Customization

The icon configuration utilizes code that is originally from ShyFox, therefore
the same settings are used (these can be set in about:config).
| Setting | true | false (default) |
| -------------------------------------- | --------------------------------------------------------------------- | ------------------------- |
| `shyfox.enable.ext.mono.toolbar.icons` | Supported extensions get monochrome icons as toolbar buttons | Standard icons used |
| `shyfox.enable.ext.mono.context.icons` | Supported extensions get monochrome icons as context menu items | Standard icons used |
| `shyfox.enable.context.menu.icons` | Many context menu items get icons | No icons in context menus |

### CSS configurations
The theme ships with a `defaults.css`. Its values can be overridden in
`config.css` next to it. In a Bash or manual installation, both files are in
`<profile>/chrome/textfox/`.

#### Defaults
```css
:root {
  --tf-font-family: "SF Mono", Consolas, monospace; /* Font family of config */
  --tf-font-size: 14px; /* Font size of config */
  --tf-accent: var(--toolbarbutton-icon-fill); /* Accent color used, eg: color when hovering a container  */
  --tf-bg: var(--lwt-accent-color, -moz-dialog); /* Background color of all elements, tab colors derive from this */
  --tf-border: var(--panel-border-color, var(--toolbar-field-background-color)); /* Border color when not hovered */
  --tf-border-transition: 0.2s ease; /* Smooth color transitions for borders */
  --tf-border-width: 2px; /* Width of borders */
  --tf-rounding: 0px; /* Border radius used through out the config */
  --tf-text-transform: none; /* Text transform to use */
  --tf-display-horizontal-tabs: none; /* If horizontal tabs should be shown, none = hidden, block = shown */
  --tf-display-window-controls: none; /* If the window controls should be shown (won't work with sidebery and hidden horizontal tabs), none = hidden, flex = shown */ 
  --tf-display-nav-buttons: none; /* If the navigation buttons (back, forward) should be shown, none = hidden, flex = shown */
  --tf-display-urlbar-icons: none; /* If the icons inside the url bar should be shown, none = hidden, flex = shown */
  --tf-display-sidebar-tools: flex; /* If the "Customize sidebar" button on the sidebar should be shown, none = hidden, flex = shown */ 
  --tf-display-titles: flex; /* If titles (tabs, navbar, main etc.) should be shown, none = hidden, flex = shown */
  --tf-newtab-logo: "   __            __  ____          \A   / /____  _  __/ /_/ __/___  _  __\A  / __/ _ \\| |/_/ __/ /_/ __ \\| |/_/\A / /_/  __/>  </ /_/ __/ /_/ />  <  \A \\__/\\___/_/|_|\\__/_/  \\____/_/|_|  ";
  --tf-navbar-margin: 8px 8px 2px; /* navbar margin */
  --tf-navbar-padding: 4px; /* navbar padding */
  --tf-bookmarks-alignment: center; /* alignment of bookmarks in the bookmarks toolbar (if you have many bookmarks, left is recommended) */
}

```

### Changing the new tab logo

The new tab logo can be any string you want, to create a string with line breaks
add a `\A` at every line break, also make sure to break any backslashes, eg. if
you want a `\`, you need to write `\\`. I used [this tool](https://www.patorjk.com/software/taag/#p=display&f=Slant&t=textfox)
to create the current logo.

Wanna hide the logo? Simply pass an empty string as the logo.

### Recipes

Here are some example changes that you can do to achieve different looks.

#### Swap positions of tabs and window controls when using horizontal tabs
```css
/* path: chrome/config.css */
:root {
  --tf-display-horizontal-tabs: inline-flex;
  --tf-display-window-controls: flex;
}
```

#### Rounded borders
```css
/* path: chrome/config.css */
:root {
  --tf-rounding: 4px;
}
```

#### Align bookmarks to the left
```css
/* path: chrome/config.css */
:root {
  --tf-bookmarks-alignment: left;
}
```

#### Adjust title margins

The titles (e.g. "tabs", "navbar", "main") are `::before` pseudo-elements positioned on the border of each container. Override the margin per selector to reposition them.

```css
/* path: chrome/config.css */
/* These are just the default values, change them to fit your needs */

/* main title */
#tabbrowser-tabbox::before {
  margin: -1.75rem 0rem !important;
}

/* navbar title */
#nav-bar::before {
  margin: -16px 8px !important;
}

/* bookmarks title */
#PersonalToolbar::before {
  margin: -1.25rem 0.4rem !important;
}

/* tools title */
.buttons-wrapper::before {
  margin: -0.85rem 0.85rem !important;
}

/* tool title */
#sidebar-box::before {
  margin: -0.85rem 0.85rem !important;
}

/* vertical tabs title */
box#vertical-tabs::before {
  margin: -1.75rem .4rem !important;
}

/* horizontal tabs title */
#TabsToolbar::before {
  margin: -1rem .75rem !important;
}

/* findbar title */
findbar::before {
  margin: -1.75rem .75rem !important;
}

/* split view panel title */
.split-view-panel::before {
  margin: -1.75rem 0rem !important;
}
```

#### Do you have a banger recipe?
Feel free to open a PR and add it here!

## Tooling

The repo ships a small toolkit under `tools/firefox-chrome/` (also
symlinked into `.claude/skills/` so AI agents pick it up automatically). It
exists to solve the hardest part of maintaining a userChrome theme: Firefox's
internal UI is real DOM with its own CSS, and the selectors/IDs change between
versions — the number one cause of theme breakage.

These scripts are plain shell/Python and work on their own, no agent required.

### `sf-search.sh` — find real selectors in the latest Firefox

Searches the latest Firefox release source (via searchfox) so you can confirm a
selector actually exists before writing CSS against it.

```sh
# Where is .urlbar-background styled?
sh tools/firefox-chrome/sf-search.sh "urlbar-background" "*.css"

# Find an element in the browser DOM
sh tools/firefox-chrome/sf-search.sh "nav-bar" "*.xhtml"
```

Output is `path:line: matched line`. Zero matches for a selector textfox already
uses is a strong hint that Firefox renamed or removed it.

### `firefox-live.sh` — inspect the live browser UI

Launches a throwaway Firefox (with textfox applied) and inspects the actual
rendered chrome DOM, then cleans up after itself. Handy on its own to identify
an element's real id/classes, its runtime state attributes (`[open]`,
`[focused]`, …), and the computed styles that won the cascade.

```sh
# Inspect the nav bar
sh tools/firefox-chrome/firefox-live.sh nav-bar

# A specific selector + the computed properties you care about
sh tools/firefox-chrome/firefox-live.sh --selector "#urlbar .urlbar-background" \
   -- --computed background-color,border,box-shadow

# Bare Firefox, without textfox applied
sh tools/firefox-chrome/firefox-live.sh --vanilla nav-bar
```

> [!NOTE]
> Requires `python3` and a Firefox install. The first run creates a small
> virtualenv at `~/.cache/textfox-firefox-live/venv` for `marionette_driver`.
> Live inspection needs a display; on headless Linux prefix the command with
> `xvfb-run -a`.

### Test the Nix profile installer in Gecko

The integration test uses Python 3.10 or later and an installed Firefox or
Waterfox. It runs offline in a new temporary profile and verifies file creation,
managed upgrades and conflict handling through Gecko's native file APIs.

```powershell
python tests/nix-profile-gecko.py "C:\Program Files\Waterfox\waterfox.exe"
```

Use the path to your browser executable. Testing the NixOS package and its
startup configuration requires running the wrapped Firefox on NixOS.

## Community

Join [#textfox:matrix.org](https://matrix.to/#/#textfox:matrix.org) for support and discussion.

## Acknowledgements

[Naezr](https://github.com/Naezr) - Icon logic and some sidebery logic.
