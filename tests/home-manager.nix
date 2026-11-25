# Build the real Home Manager file tree without activating a user profile.
let
  textfox = builtins.getFlake (toString ../.);
  hm = builtins.getFlake "github:nix-community/home-manager/6480d7d8533b88c78cc6dcda395ab89cd546e450";
  pkgs = textfox.inputs.nixpkgs.legacyPackages.${builtins.currentSystem};
  home = hm.lib.homeManagerConfiguration {
    inherit pkgs;
    modules = [
      textfox.homeManagerModules.default
      {
        home = {
          username = "tester";
          homeDirectory = "/home/tester";
          stateVersion = "26.05";
          fileOverlapResolution = "error";
        };
        programs.firefox = {
          configPath = ".test-firefox";
          profiles = {
            work = {
              path = "abc.work";
              userChrome = "/* custom chrome */";
              userContent = ../chrome/content/about.css;
            };
            plain.id = 1;
            other.id = 2;
          };
        };
        textfox = {
          enable = true;
          config.density = "comfortable";
          config.colors.menu = {
            background = "Canvas";
            text = "CanvasText";
          };
          profiles = [
            "work"
            "plain"
          ];
        };
      }
    ];
  };
in
pkgs.runCommand "textfox-home-manager-profiles" { } ''
  cd "${home.config.home-files}/.test-firefox"
  test ! -e work/chrome
  test ! -e other/chrome
  for profile in abc.work plain; do
    for entry in userChrome userContent; do
      cmp "$profile/chrome/textfox-$entry.css" "${../chrome}/$entry.css"
      head -n1 "$profile/chrome/$entry.css" | grep -Fx "@import url(\"textfox-$entry.css\");"
    done
    grep -F -- '--tf-density: 1.25;' "$profile/chrome/config.css"
    grep -F -- '--tf-menu-background: Canvas;' "$profile/chrome/config.css"
    grep -F -- '--tf-menu-text: CanvasText;' "$profile/chrome/config.css"
    test -s "$profile/chrome/content/newtab.css"
    test -s "$profile/chrome/icons/tab.svg"
  done
  for entry in userChrome userContent; do
    tail -n1 "abc.work/chrome/$entry.css" | grep -Fx "@import url(\"profile-$entry.css\");"
    test "$(wc -l < "plain/chrome/$entry.css")" -eq 1
  done
  grep -Fx '/* custom chrome */' abc.work/chrome/profile-userChrome.css
  cmp abc.work/chrome/profile-userContent.css "${../chrome/content/about.css}"
  touch "$out"
''
