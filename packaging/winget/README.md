# Manifestos winget (modelo)

Este diretório contém os três manifestos winget do CurlCommander. Eles são um
**modelo de release**: os campos de versão e o `InstallerSha256` precisam ser
preenchidos com valores reais antes de submeter ao repositório oficial
[`microsoft/winget-pkgs`](https://github.com/microsoft/winget-pkgs).

## Como preencher a cada release

1. Publique a release `vX.Y.Z` com o binário `curlcmd.exe` e o arquivo
   `SHA256SUMS` (a workflow de release já faz isso).
2. Pegue o SHA256 do `curlcmd.exe` no arquivo `SHA256SUMS`.
3. Nos três arquivos, troque `0.2.0` pela versão publicada e, no
   `*.installer.yaml`, troque `REPLACE_WITH_SHA256` pelo hash real.
4. Valide localmente:

   ```powershell
   winget validate --manifest packaging\winget
   ```

5. Submeta via `wingetcreate` ou abra um PR em `microsoft/winget-pkgs`.

## Instalação pelo usuário final (depois de publicado)

```powershell
winget install Ivomsantiago.CurlCommander
```

O pacote instala apenas o binário standalone. Recursos que dependem de Python
(validadores em navegador, proxy interceptador, download de payloads) exigem
uma instalação via Python — rode `curlcmd doctor` para o diagnóstico.
