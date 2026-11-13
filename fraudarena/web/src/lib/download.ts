// Start a browser download of a URL (the server sends Content-Disposition: attachment).
export function downloadUrl(url: string) {
  const a = document.createElement("a");
  a.href = url; a.download = ""; a.rel = "noopener";
  document.body.appendChild(a); a.click(); a.remove();
}

export async function readJsonFile(file: File): Promise<any> {
  return JSON.parse(await file.text());
}
