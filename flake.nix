{
  description = "Firefox theme for the tui enthusiast";

  inputs = {
    nixpkgs.url = "github:NixOS/nixpkgs?ref=nixos-26.05";
  };

  outputs =
    { self, nixpkgs, ... }@inputs:
    let
      systems = [
        "x86_64-linux"
        "aarch64-linux"
        "x86_64-darwin"
        "aarch64-darwin"
      ];
      linuxSystems = builtins.filter (nixpkgs.lib.hasSuffix "-linux") systems;
      forAllSystems = nixpkgs.lib.genAttrs systems;
      pkgsForEach = nixpkgs.legacyPackages;
    in
    {
      packages = forAllSystems (system: {
        default = pkgsForEach.${system}.callPackage ./nix/pkgs/default.nix { };
      });

      lib.wrapTextfox = forAllSystems (
        system: pkgsForEach.${system}.callPackage ./nix/pkgs/wrapTextfox.nix { }
      );

      nixosModules.default = self.nixosModules.textfox; # convention
      nixosModules.textfox = import ./nix/modules/nixos.nix inputs;

      homeManagerModules.default = self.homeManagerModules.textfox;
      homeManagerModules.textfox = import ./nix/modules/home-manager.nix;

      checks = nixpkgs.lib.genAttrs linuxSystems (
        system:
        let
          testSystem = nixpkgs.lib.nixosSystem {
            modules = [
              self.nixosModules.default
              {
                nixpkgs.hostPlatform = system;
                system.stateVersion = "26.05";
                textfox.enable = true;
              }
            ];
          };
        in
        {
          nixosWrapper =
            nixpkgs.lib.findFirst (package: nixpkgs.lib.getName package == "textfox")
              (throw "The Textfox NixOS module did not add a wrapped Firefox package")
              testSystem.config.environment.systemPackages;
        }
      );
    };
}
