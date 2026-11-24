{
  config,
  lib,
  ...
}:
let
  cfg = config.textfox;
  firefox = config.programs.firefox;
  assets = lib.cleanSourceWith {
    src = ../../chrome;
    filter =
      path: _:
      !builtins.elem (baseNameOf path) [
        "userChrome.css"
        "userContent.css"
        "config.css"
      ];
  };

  profileFiles =
    name:
    let
      profile = firefox.profiles.${name};
      chrome = "${firefox.profilesPath}/${profile.path}/chrome";
      entryFiles =
        option:
        let
          file = "${option}.css";
          custom = profile.${option} != "";
        in
        {
          "${chrome}/textfox-${file}".source = ../../chrome + "/${file}";
          # Keep Home Manager's text or path source intact, beside the entry
          # point so relative URLs and imports in the user's CSS still resolve.
          "${chrome}/${file}" = lib.mkIf custom { target = "${chrome}/profile-${file}"; };
          "${chrome}/textfox-entry-${file}" = {
            target = "${chrome}/${file}";
            text =
              ''
                @import url("textfox-${file}");
              ''
              + lib.optionalString custom ''
                @import url("profile-${file}");
              '';
          };
        };
    in
    lib.mkMerge [
      {
        "${chrome}" = {
          source = assets;
          recursive = true;
        };
        "${chrome}/config.css".text = cfg.configCss;
      }
      (entryFiles "userChrome")
      (entryFiles "userContent")
    ];
in
{

  imports = [
    ./options.nix
    (lib.mkChangedOptionModule [ "textfox" "profile" ] [ "textfox" "profiles" ] (
      config:
      let
        profile = lib.getAttrFromPath [ "textfox" "profile" ] config;

      in
      [ profile ]
    ))
  ];

  options.textfox = {
    profiles = lib.mkOption {
      type = with lib.types; listOf str;
      default = [ ];
      description = "List of Firefox profiles to apply the textfox configuration to";
    };
  };

  config = lib.mkIf cfg.enable {
    programs.firefox = {
      enable = true;
      profiles = lib.mkMerge (
        map (profile: {
          "${profile}".extraConfig = builtins.readFile ../../user.js;
        }) cfg.profiles
      );
    };

    home.file = lib.mkMerge (map profileFiles cfg.profiles);
  };
}
