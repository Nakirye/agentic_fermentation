{
  description = "Fermentation Planner Agent – dev shell";

  inputs = {
    nixpkgs.url = "github:NixOS/nixpkgs/nixos-unstable";
  };

  outputs = { self, nixpkgs }:
    let
      systems = [ "x86_64-linux" "aarch64-linux" ];
      forAllSystems = f: nixpkgs.lib.genAttrs systems (system: f nixpkgs.legacyPackages.${system});
    in
    {
      devShells = forAllSystems (pkgs:
        let
          python = pkgs.python313.withPackages (ps: with ps; [
            pydantic
            pytest
            openai
            python-dotenv
          ]);
        in
        {
          default = pkgs.mkShell {
            packages = [ python ];

            shellHook = ''
              export PYTHONDONTWRITEBYTECODE=1
              echo "🍕 $(python --version) dev shell ready"
            '';
          };
        });
    };
}
