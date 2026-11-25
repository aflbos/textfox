{
  lib,
  config,
  ...
}:
let
  inherit (lib.options) mkOption mkEnableOption;
  inherit (lib.modules) mkRenamedOptionModule;
  inherit (lib.modules) mkRemovedOptionModule;
  inherit (lib.strings) replaceStrings;
  inherit (lib.types) bool str;

  cfg = config.textfox.config;
  colorAreas = [
    "menu"
    "sidebar"
    "statusbar"
  ];
  densityScale = {
    compact = "0.75";
    standard = "1";
    comfortable = "1.25";
  };
in
{
  imports = [
    (mkRenamedOptionModule
      [ "textfox" "config" "displayHorizontalTabs" ]
      [ "textfox" "config" "tabs" "horizontal" "enable" ]
    )
    (mkRemovedOptionModule [
      "textfox"
      "config"
      "tabs"
      "vertical"
      "sidebery"
    ] "Sidebery support was dropped in textfox.")
  ];

  options.textfox = {
    enable = mkEnableOption "Textfox.";

    config = {
      displayWindowControls = mkEnableOption "window controls.";
      displayNavButtons = mkEnableOption "back and forward navigation buttons in the Firefox UI.";
      displayUrlbarIcons = mkEnableOption "page actions inside the address bar.";
      displayUrlbarIndicators = mkEnableOption "tracking protection and container indicators in the address bar." // {
        default = true;
      };
      displaySidebarTools = mkEnableOption "sidebar tools section." // {
        default = true;
      };

      displayTitles = mkOption {
        type = bool;
        default = true;
        description = "If titles (tabs, navbar, main etc.) should be shown";
      };

      newtabLogo = mkOption {
        type = str;
        default = ''
             __            __  ____
             / /____  _  __/ /_/ __/___  _  __
            / __/ _ \| |/ / __/ /_/ __ \| |/ /
          / /_/  __/>  </ /_/ __/ /_/ />  <
          \__/\___/_/|_|\__/_/  \____/_/|_|
        '';
        apply = p: replaceStrings [ "\n" "\\" ] [ "\\A" "\\\\" ] p;
        description = "ASCII logo used for new tab page";
      };

      background.color = mkOption {
        type = str;
        default = "var(--lwt-accent-color, -moz-dialog)";
        description = "Background color of all elements.";
      };

      colors = lib.genAttrs colorAreas (area: {
        background = mkOption {
          type = lib.types.nullOr str;
          default = null;
          description = "CSS background color for the ${area}. Defaults to the Textfox background.";
        };
        text = mkOption {
          type = lib.types.nullOr str;
          default = null;
          description = "CSS text color for the ${area}. Defaults to the active theme foreground.";
        };
      });

      font = {
        family = mkOption {
          type = str;
          default = "\"SF Mono\", Consolas, monospace";
          description = "Default font family";
        };
        size = mkOption {
          type = str;
          default = "14px";
          description = "The font size to use";
        };
        accent = mkOption {
          type = str;
          default = "var(--toolbarbutton-icon-fill)";
          description = "The accent color to use";
        };
      };

      border = {
        color = mkOption {
          type = str;
          default = "var(--panel-border-color, var(--toolbar-field-background-color))";
          description = "Border color when not hovered";
        };
        transition = mkOption {
          type = str;
          default = "0.2s ease";
          description = "Color transitions for borders";
        };
        width = mkOption {
          type = str;
          default = "2px";
          description = "Width of borders";
        };
        radius = mkOption {
          type = str;
          default = "0px";
          description = "Border radius used throughout the config";
        };
      };

      icons = {
        toolbar.extensions.enable = mkEnableOption "monochrome extension toolbar buttons.";
        context.extensions.enable = mkEnableOption "monochrome extension context menu items.";
        context.firefox.enable = mkEnableOption "icons for common context menu items.";
      };

      tabs = {
        horizontal.enable = mkOption {
          type = lib.types.nullOr bool;
          default = null;
          description = "Show the horizontal tab bar. By default, follow the browser's tab orientation.";
        };
        vertical.enable = mkEnableOption "display of vertical tabs." // {
          default = true;
        };
      };

      extraConfig = mkOption {
        type = str;
        default = "";
        description = "Extra lines to add to config.css";
      };

      textTransform = mkOption {
        type = str;
        default = "none";
        description = "Text transform to use";
      };

      density = mkOption {
        type = lib.types.enum [
          "browser"
          "compact"
          "standard"
          "comfortable"
        ];
        default = "browser";
        description = "Spacing preset for the browser interface. By default, follow the browser density.";
      };

      navbar = {
        margin = mkOption {
          type = str;
          default = "calc(8px * var(--tf-density)) calc(8px * var(--tf-density)) calc(2px * var(--tf-density))";
          description = "Navbar margin";
        };
        padding = mkOption {
          type = str;
          default = "calc(4px * var(--tf-density))";
          description = "Navbar padding";
        };
      };

      bookmarks.alignment = mkOption {
        type = str;
        default = "center";
        description = "Alignment of bookmarks in the bookmarks toolbar (if you have many bookmarks, left is recommended)";
      };

      statusbar = {
        margin = mkOption {
          type = str;
          default = "calc(6px * var(--tf-density)) calc(8px * var(--tf-density)) calc(8px * var(--tf-density))";
          description = "Margin of the Waterfox status bar";
        };
        padding = mkOption {
          type = str;
          default = "calc(4px * var(--tf-density))";
          description = "Padding of the Waterfox status bar";
        };
      };

      animation.duration = mkOption {
        type = str;
        default = "150ms";
        description = "Duration of tab, urlbar, status bar and menu animations";
      };
    };

    configCss = mkOption {
      readOnly = true;
      visible = false;
      type = str;
      default = ''
        :root {
          --tf-font-family: ${cfg.font.family};
          --tf-font-size: ${cfg.font.size};
          ${lib.optionalString (cfg.density != "browser") "--tf-density: ${densityScale.${cfg.density}};"}
          --tf-accent: ${cfg.font.accent};
          --tf-bg: ${cfg.background.color};
          ${lib.concatMapStringsSep "\n          " (
            area:
            let
              colors = cfg.colors.${area};
            in
            lib.optionalString (colors.background != null) "--tf-${area}-background: ${colors.background};"
            + lib.optionalString (colors.text != null) "\n          --tf-${area}-text: ${colors.text};"
          ) colorAreas}
          --tf-border: ${cfg.border.color};
          --tf-border-transition: ${cfg.border.transition};
          --tf-border-width: ${cfg.border.width};
          --tf-rounding: ${cfg.border.radius};
          --tf-text-transform: ${cfg.textTransform};
          ${lib.optionalString (cfg.tabs.horizontal.enable != null) "--tf-display-horizontal-tabs: ${if cfg.tabs.horizontal.enable then "block" else "none"};"}
          --tf-display-window-controls: ${if cfg.displayWindowControls then "flex" else "none"};
          --tf-display-nav-buttons: ${if cfg.displayNavButtons then "flex" else "none"};
          --tf-display-urlbar-icons: ${if cfg.displayUrlbarIcons then "initial" else "none"};
          --tf-display-urlbar-indicators: ${if cfg.displayUrlbarIndicators then "initial" else "none"};
          --tf-display-sidebar-tools: ${if cfg.displaySidebarTools then "flex" else "none"};
          --tf-display-titles: ${if cfg.displayTitles then "flex" else "none"};
          --tf-newtab-logo: "${cfg.newtabLogo}";
          --tf-navbar-margin: ${cfg.navbar.margin};
          --tf-navbar-padding: ${cfg.navbar.padding};
          --tf-bookmarks-alignment: ${cfg.bookmarks.alignment};
          --tf-statusbar-margin: ${cfg.statusbar.margin};
          --tf-statusbar-padding: ${cfg.statusbar.padding};
          --tf-animation-duration: ${cfg.animation.duration};
        }
        ${cfg.extraConfig}
      '';
    };
  };
}
