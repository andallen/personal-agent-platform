import "./messages.css";
export function UserMessage({ text }: { text: string }) {
  return <div className="msg-user">{text}</div>;
}
