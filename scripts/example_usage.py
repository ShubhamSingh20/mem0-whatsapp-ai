# from service.assistant_layer import AssistantLayer


# assistant_layer = AssistantLayer()

# message_with_media = assistant_layer.process_whatsapp_message(data)

# print(message_with_media)


from service.mem0_service import Mem0Service

mem0_service = Mem0Service()

a = mem0_service.search_memories("1", "websites visited")

for i in a:
    print(i['memory'])
# from service.mem0_service import Mem0Service

# mem0_service = Mem0Service()

# memories = mem0_service.get_all_memories("1")


# print(mem0_service.search_memories("1", "screenshots"))