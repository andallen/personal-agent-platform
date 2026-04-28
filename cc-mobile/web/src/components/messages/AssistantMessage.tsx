import { marked } from "marked";
import DOMPurify from "dompurify";
import "./messages.css";

marked.setOptions({ breaks: true, gfm: true });

export function AssistantMessage({ text }: { text: string }) {
  const html = marked.parse(text) as string;
  const safe = DOMPurify.sanitize(html);
  return <div className="msg-assistant" dangerouslySetInnerHTML={{ __html: safe }} />;
}
