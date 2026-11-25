{
  lib,
  wrapFirefox,
  runCommandLocal,
}:
browser:
{
  configCss ? "",
  extraUserChrome ? "",
  extraUserContent ? "",
  ...
}@args:
let

  textfoxChrome =
    runCommandLocal "textfox-chrome"
      {
        inherit configCss extraUserChrome extraUserContent;
        passAsFile = [
          "configCss"
          "extraUserChrome"
          "extraUserContent"
        ];

        src = ./../../chrome;
      }
      ''
        bash ${./bundle-stylesheets.sh} "$src" "$out" \
          "$configCssPath" "$extraUserChromePath" "$extraUserContentPath"
      '';

  configScript = builtins.readFile ./install-profile.js + ''
    // Needed prefs to use textfox
    pref("toolkit.legacyUserProfileCustomizations.stylesheets", true);
    pref("svg.context-properties.content.enabled", true);
    pref("layout.css.has-selector.enabled", true);

    installTextfoxProfile("${textfoxChrome}");
  '';

in
wrapFirefox browser (
  lib.removeAttrs args [
    "configCss"
    "extraUserChrome"
    "extraUserContent"
  ]
  // {
    pname = args.pname or "textfox";
    extraPrefs = configScript + (args.extraPrefs or "");
    # The packaged AutoConfig needs Gecko file APIs to manage its profile stylesheets.
    extraAutoConfig = (args.extraAutoConfig or "") + ''
      pref("general.config.sandbox_enabled", false);
    '';
  }
)
