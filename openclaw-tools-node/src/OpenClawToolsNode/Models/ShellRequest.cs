namespace OpenClawToolsNode.Models;

public class ShellRequest
{
    public required string Command { get; set; }
    public string? WorkingDirectory { get; set; }
    public int TimeoutMs { get; set; } = 30000;
}
