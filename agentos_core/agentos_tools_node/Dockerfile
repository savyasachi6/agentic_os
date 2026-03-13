FROM mcr.microsoft.com/dotnet/sdk:10.0 AS build
WORKDIR /src

# Copy csproj and restore
COPY ["src/AgentOSToolsNode/AgentOSToolsNode.csproj", "AgentOSToolsNode/"]
RUN dotnet restore "AgentOSToolsNode/AgentOSToolsNode.csproj"

# Copy full source and build
COPY src/AgentOSToolsNode/ AgentOSToolsNode/
WORKDIR "/src/AgentOSToolsNode"
RUN dotnet build "AgentOSToolsNode.csproj" -c Release -o /app/build

FROM build AS publish
RUN dotnet publish "AgentOSToolsNode.csproj" -c Release -o /app/publish /p:UseAppHost=false

FROM mcr.microsoft.com/dotnet/aspnet:10.0 AS final
WORKDIR /app
COPY --from=publish /app/publish .
EXPOSE 8080
ENTRYPOINT ["dotnet", "AgentOSToolsNode.dll"]
