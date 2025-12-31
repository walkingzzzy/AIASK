/**
 * 分组管理组件
 */
import React, { useState } from 'react'
import { Card, List, Button, Input, Modal, Space, Popconfirm, message } from 'antd'
import {
  PlusOutlined,
  EditOutlined,
  DeleteOutlined,
  FolderOutlined
} from '@ant-design/icons'
import { useWatchlistStore } from '@/stores/useWatchlistStore'

export const GroupManager: React.FC = () => {
  const {
    groups,
    currentGroupId,
    addGroup,
    removeGroup,
    renameGroup,
    setCurrentGroup
  } = useWatchlistStore()

  const [addModalVisible, setAddModalVisible] = useState(false)
  const [editModalVisible, setEditModalVisible] = useState(false)
  const [newGroupName, setNewGroupName] = useState('')
  const [editingGroupId, setEditingGroupId] = useState<string | null>(null)
  const [editingGroupName, setEditingGroupName] = useState('')

  // 添加分组
  const handleAddGroup = () => {
    if (!newGroupName.trim()) {
      message.warning('请输入分组名称')
      return
    }

    addGroup(newGroupName.trim())
    message.success('分组创建成功')
    setNewGroupName('')
    setAddModalVisible(false)
  }

  // 重命名分组
  const handleRenameGroup = () => {
    if (!editingGroupId || !editingGroupName.trim()) {
      message.warning('请输入分组名称')
      return
    }

    renameGroup(editingGroupId, editingGroupName.trim())
    message.success('重命名成功')
    setEditModalVisible(false)
    setEditingGroupId(null)
    setEditingGroupName('')
  }

  // 删除分组
  const handleDeleteGroup = (groupId: string) => {
    if (groupId === 'default') {
      message.warning('默认分组不能删除')
      return
    }

    removeGroup(groupId)
    message.success('分组已删除')
  }

  // 打开编辑弹窗
  const openEditModal = (groupId: string, groupName: string) => {
    setEditingGroupId(groupId)
    setEditingGroupName(groupName)
    setEditModalVisible(true)
  }

  return (
    <>
      <Card
        title="分组管理"
        extra={
          <Button
            type="text"
            size="small"
            icon={<PlusOutlined />}
            onClick={() => setAddModalVisible(true)}
          >
            新建
          </Button>
        }
      >
        <List
          dataSource={groups}
          renderItem={group => (
            <List.Item
              style={{
                cursor: 'pointer',
                padding: '10px 12px',
                borderRadius: 8,
                marginBottom: 4,
                background: currentGroupId === group.id ? 'rgba(88, 166, 255, 0.15)' : 'transparent',
                borderLeft: currentGroupId === group.id ? '3px solid #58a6ff' : '3px solid transparent',
                transition: 'all 0.2s ease',
              }}
              onMouseEnter={(e) => {
                if (currentGroupId !== group.id) {
                  e.currentTarget.style.background = 'rgba(255, 255, 255, 0.05)'
                }
              }}
              onMouseLeave={(e) => {
                if (currentGroupId !== group.id) {
                  e.currentTarget.style.background = 'transparent'
                }
              }}
              onClick={() => setCurrentGroup(group.id)}
            >
              <div className="flex items-center justify-between w-full">
                <Space>
                  <FolderOutlined style={{ color: currentGroupId === group.id ? '#58a6ff' : '#8b949e' }} />
                  <span style={{ 
                    fontWeight: 500, 
                    color: currentGroupId === group.id ? '#e6edf3' : '#8b949e' 
                  }}>
                    {group.name}
                  </span>
                  <span style={{ color: '#6e7681', fontSize: 12 }}>
                    ({group.stocks.length})
                  </span>
                </Space>

                {group.id !== 'default' && (
                  <Space size="small">
                    <Button
                      type="text"
                      size="small"
                      icon={<EditOutlined />}
                      onClick={(e) => {
                        e.stopPropagation()
                        openEditModal(group.id, group.name)
                      }}
                    />
                    <Popconfirm
                      title="确定删除此分组吗？"
                      description="分组中的股票也将被删除"
                      onConfirm={(e) => {
                        e?.stopPropagation()
                        handleDeleteGroup(group.id)
                      }}
                      onCancel={(e) => e?.stopPropagation()}
                      okText="确定"
                      cancelText="取消"
                    >
                      <Button
                        type="text"
                        size="small"
                        danger
                        icon={<DeleteOutlined />}
                        onClick={(e) => e.stopPropagation()}
                      />
                    </Popconfirm>
                  </Space>
                )}
              </div>
            </List.Item>
          )}
        />
      </Card>

      {/* 添加分组弹窗 */}
      <Modal
        title="新建分组"
        open={addModalVisible}
        onOk={handleAddGroup}
        onCancel={() => {
          setAddModalVisible(false)
          setNewGroupName('')
        }}
        okText="确定"
        cancelText="取消"
      >
        <Input
          placeholder="请输入分组名称"
          value={newGroupName}
          onChange={(e) => setNewGroupName(e.target.value)}
          onPressEnter={handleAddGroup}
          maxLength={20}
        />
      </Modal>

      {/* 重命名分组弹窗 */}
      <Modal
        title="重命名分组"
        open={editModalVisible}
        onOk={handleRenameGroup}
        onCancel={() => {
          setEditModalVisible(false)
          setEditingGroupId(null)
          setEditingGroupName('')
        }}
        okText="确定"
        cancelText="取消"
      >
        <Input
          placeholder="请输入新的分组名称"
          value={editingGroupName}
          onChange={(e) => setEditingGroupName(e.target.value)}
          onPressEnter={handleRenameGroup}
          maxLength={20}
        />
      </Modal>
    </>
  )
}
