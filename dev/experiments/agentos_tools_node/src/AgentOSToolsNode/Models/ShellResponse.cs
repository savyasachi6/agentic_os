namespace AgentOSToolsNode.Models;

public class ShellResponse
{
    public int ExitCode { get; set; }
    public required string Stdout { get; set; }
    public required string Stderr { get; set; }
}
