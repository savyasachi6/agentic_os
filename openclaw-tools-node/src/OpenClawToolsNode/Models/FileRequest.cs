namespace OpenClawToolsNode.Models;

public class FileRequest
{
    public required string Path { get; set; }
    public string? Content { get; set; } // Used for write operations
}
