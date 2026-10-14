import type { ReactNode } from "react"
import { Icon } from "./Icon"
import type { IconName } from "../../types"

interface ButtonProps {
  children: ReactNode
  kind?: "primary" | "secondary" | "ghost" | "danger"
  icon?: IconName
  onClick?: () => void
  type?: "button" | "submit"
  disabled?: boolean
  className?: string
}

export function Button({
  children,
  kind = "primary",
  icon,
  onClick,
  type = "button",
  disabled = false,
  className = "",
}: ButtonProps) {
  return (
    <button
      className={`button ${kind} ${className}`}
      onClick={onClick}
      type={type}
      disabled={disabled}
    >
      {icon && <Icon name={icon} size={16} />}
      {children}
    </button>
  )
}

